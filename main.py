import discord
import os
from discord.ext import commands
from discord import MessageType
from discord.ext.commands import has_role, MissingPermissions
from discord.ext.commands.errors import MissingRole
from discord_slash import SlashCommand, SlashContext
from discord_slash.utils import manage_commands
from replit import db
from keep_alive import keep_alive

bot = commands.Bot(command_prefix="!")
slash = SlashCommand(bot, sync_commands=True)

guild_ids = [int(guild) for guild in os.getenv("GUILD_IDS").split(",")]


@bot.event
async def on_ready():
    print(f"{bot.user} has come online...")


@bot.event
async def on_message(message):
    if message.type == MessageType.pins_add and message.author.bot:
        await message.delete()


@bot.event
async def on_slash_command_error(ctx, error):
    await ctx.respond(eat=True)
    if isinstance(error, MissingPermissions):
        await ctx.send("You are missing permission(s) to run this command.", delete_after=5)
    elif isinstance(error, MissingRole):
        await ctx.send("You are missing role(s) to run this command.", delete_after=5)
    else:
        raise error


@slash.slash(name="queue",
             description="Controls the status of the queue",
             options=[manage_commands.create_option(
                 name="state",
                 description="Set the queue to this state",
                 option_type=4,
                 required=True,
                 choices=[{"name": "open", "value": 1}, {"name": "close", "value": 1}])
             ],
             guild_ids=guild_ids)
@has_role("Lab Assistant")
async def _queue(ctx: SlashContext, state: int):
    """Manage the queue"""
    if state == 0:
        await close_queue(ctx)
    elif state == 1:
        await open_queue(ctx)


async def open_queue(ctx):
    emojis = ["✅", "❓"]
    set_key("queue_status", ctx.guild, True)
    await ctx.respond(eat=True)
    message = await ctx.send(
        f">>> :clipboard: __**Lab Queue**__\n*The queue is now open!*\n\nTo get signed off click {emojis[0]}\nTo get "
        f"help click {emojis[1]}")
    for emoji in emojis:
        await message.add_reaction(emoji)
    await delete_queue_message(ctx.guild)
    await message.pin()
    set_key("queue_message", ctx.guild, [ctx.channel.guild, message.guild])


async def close_queue(ctx):
    set_key("queue_status", ctx.guild, False)
    await ctx.respond(eat=True)
    message = await ctx.send(
        ">>> :x: __**Lab Queue**__\n*The queue is now closed.*\n\nCome back next time to get signed off :slight_smile:")
    await delete_queue_message(ctx.guild)
    await message.pin()
    set_key("queue_message", ctx.guild, [ctx.channel.guild, message.guild])


async def delete_queue_message(guild: discord.guild):
    if old_message := get_key("queue_message", guild):
        try:
            await bot.http.delete_message(old_message[0], old_message[1])
        except:
            pass


def get_key(key: str, guild: discord.guild, value_if_none=None):
    if str(guild.guild) + key in db.prefix(guild.guild):
        return db[f"{guild.guild}{key}"]
    else:
        if value_if_none is not None:
            set_key(key, guild, value_if_none)
            return value_if_none
        else:
            return None


def set_key(key: str, guild: discord.guild, value):
    db[f"{guild.guild}{key}"] = value


def del_key(key: str, guild: discord.guild):
    if key in db.prefix(guild.guild):
        del db[f"{guild.guild}{key}"]


keep_alive()
bot.run(os.getenv("TOKEN"))
