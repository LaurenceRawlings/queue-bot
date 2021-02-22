import discord
import os
from discord.ext import commands
from discord import MessageType
from discord.ext.commands import has_role, MissingPermissions
from discord.ext.commands.errors import MissingRole
from discord_slash import SlashCommand, SlashContext
from discord_slash.utils import manage_commands
from keep_alive import keep_alive
from database import db


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
        await send_error(ctx, "You are missing permission(s) to run this command.")
    elif isinstance(error, MissingRole):
        await send_error(ctx, "You are missing role(s) to run this command.")
    else:
        raise error


@bot.event
async def on_voice_state_update(ctx, before, after):
    sign_off_channel = db.get(ctx.guild.id, "add_sign_off_channel")
    help_channel = db.get(ctx.guild.id, "add_help_channel")
    waiting_channel = db.get(ctx.guild.id, "add_waiting_channel")

    channel = after.channel
    old_channel = before.channel

    if channel is not None:
        if channel.id in [sign_off_channel, help_channel, waiting_channel]:
            new_channel = await create_temp_channel(ctx.guild, room_name(ctx.display_name), "voice", channel.category)
            await ctx.edit(voice_channel=new_channel)

            if channel.id in [sign_off_channel, help_channel]: 
                category_id = db.get(ctx.guild.id, "room_chat_category")
                category = discord.utils.get(ctx.guild.categories, id=category_id)
                await create_temp_channel(ctx.guild, room_name(ctx.display_name), "text", category=category, parent_id=new_channel.id)


    if old_channel is not None:
        temp_ids = [int(temp.id) for temp in db.guild_ref(ctx.guild.id).collection("temp_channels").stream()]
        # User left a temp channel
        if old_channel.id in temp_ids:
            if len(old_channel.members) == 0:
                await delete_temp_channel(ctx.guild, old_channel.id)


@slash.slash(name="queue",
             description="Controls the status of the queue",
             options=[manage_commands.create_option(
                 name="state",
                 description="Set the queue to this state",
                 option_type=4,
                 required=True,
                 choices=[{"name": "open", "value": 1}, {"name": "close", "value": 0}])
             ],
             guild_ids=guild_ids)
@has_role("Lab Assistant")
async def _queue(ctx: SlashContext, state: int):
    """Manage the queue"""
    if state == 0:
        await close_queue(ctx)
    elif state == 1:
        await open_queue(ctx)


@slash.slash(name="set",
             description="Set options for LabBot",
             options=[manage_commands.create_option(
                 name="signoffchannel",
                 description="Set the voice channel for creating sign off rooms",
                 option_type=7,
                 required=False),

                 manage_commands.create_option(
                 name="helpchannel",
                 description="Set the voice channel for creating help rooms",
                 option_type=7,
                 required=False),

                 manage_commands.create_option(
                 name="waitingchannel",
                 description="Set the voice channel for creating waiting rooms",
                 option_type=7,
                 required=False),

                 manage_commands.create_option(
                 name="roomchatcategory",
                 description="Set the category for room chats",
                 option_type=7,
                 required=False)
             ],
             guild_ids=guild_ids)
@has_role("Admin")
async def _set(ctx: SlashContext, signoffchannel=None, helpchannel=None, waitingchannel=None, roomchatcategory=None):
    await ctx.respond(eat=True)
    # TODO: sign off and help channels can't be the same
    if signoffchannel is not None:
        if isinstance(signoffchannel, discord.channel.VoiceChannel):
            db.set(ctx.guild.id, "add_sign_off_channel", signoffchannel.id)
            await send_info(ctx, "Add sign off channel changed successfully!")
        else:
            await send_error(ctx, "The channel must be a voice channel.")
    if helpchannel is not None:
        if isinstance(helpchannel, discord.channel.VoiceChannel):
            db.set(ctx.guild.id, "add_help_channel", helpchannel.id)
            await send_info(ctx, "Add help channel changed successfully!")
        else:
            await send_error(ctx, "The channel must be a voice channel.")
    if waitingchannel is not None:
        if isinstance(waitingchannel, discord.channel.VoiceChannel):
            db.set(ctx.guild.id, "add_waiting_channel", waitingchannel.id)
            await send_info(ctx, "Add waiting channel changed successfully!")
        else:
            await send_error(ctx, "The channel must be a voice channel.")
    if roomchatcategory is not None:
        if isinstance(roomchatcategory, discord.channel.CategoryChannel):
            db.set(ctx.guild.id, "room_chat_category", roomchatcategory.id)
            await send_info(ctx, "Room chat category changed successfully!")
        else:
            await send_error(ctx, "The channel must be a category.")


async def create_temp_channel(guild: discord.Guild, name: str, channel_type, category=None, position: int = None, overwrites=None, parent_id = None):
    from firebase_admin import firestore

    if (channel_type == "voice"):
        channel = await guild.create_voice_channel(name, category=category, position=position, overwrites=overwrites)
    else:
        channel = await guild.create_text_channel(name, category=category, position=position, overwrites=overwrites)

    if parent_id is None:
        temp_ref =  db.guild_ref(guild.id).collection("temp_channels").document(str(channel.id))
        temp_ref.set({"related": []})
    else:
        temp_ref =  db.guild_ref(guild.id).collection("temp_channels").document(str(parent_id))
        if temp_ref.get() is None: 
            temp_ref.set({"related": []})
        temp_ref.update({"related": firestore.ArrayUnion([channel.id])})
    
    return channel


async def delete_temp_channel(guild: discord.Guild, channel_id: int):
    channel = guild.get_channel(channel_id)
    if channel is not None: 
        await channel.delete()
    temp_ref = db.guild_ref(guild.id).collection("temp_channels").document(str(channel.id))
    if (temp := temp_ref.get()) is None: return
    try:
        related_ids = temp.to_dict()["related"]
        for related_id in related_ids:
            related = guild.get_channel(related_id)
            if related is not None: 
                await related.delete()
    except:
        pass
    temp_ref.delete()


def room_name(username: str):
    if username[-1] == "s":
        return f"{username}' Room"
    else:
        return f"{username}'s Room"


async def open_queue(ctx):
    emojis = ["✅", "❓"]
    db.set(ctx.guild.id, "queue_status", True)
    await ctx.respond(eat=True)
    message = await ctx.send(
        f">>> :clipboard: __**Lab Queue**__\n*The queue is now open!*\n\nTo get signed off click {emojis[0]}\nTo get "
        f"help click {emojis[1]}")
    for emoji in emojis:
        await message.add_reaction(emoji)
    await delete_queue_message(ctx.guild)
    await message.pin()
    db.set(ctx.guild.id, "queue_message", [ctx.channel.id, message.id])
    waiting_room = ctx.guild.get_channel(db.get(ctx.guild.id, "add_waiting_channel"))
    await waiting_room.set_permissions(ctx.guild.default_role, overwrite=None)


async def close_queue(ctx):
    db.set(ctx.guild.id, "queue_status", False)
    await ctx.respond(eat=True)
    message = await ctx.send(
        ">>> :x: __**Lab Queue**__\n*The queue is now closed.*\n\nCome back next time to get signed off :slight_smile:")
    await delete_queue_message(ctx.guild)
    await message.pin()
    db.set(ctx.guild.id, "queue_message", [ctx.channel.id, message.id])
    waiting_room = ctx.guild.get_channel(db.get(ctx.guild.id, "add_waiting_channel"))
    await waiting_room.set_permissions(ctx.guild.default_role, view_channel=False)


async def delete_queue_message(guild: discord.guild):
    if old_message := db.get(guild.id, "queue_message", [0, 0]):
        try:
            await bot.http.delete_message(old_message[0], old_message[1])
        except:
            pass


async def send_error(ctx, message):
    await ctx.send(f"❌ {message}", hidden=True)


async def send_info(ctx, message):
    await ctx.send(f"ℹ️ {message}", hidden=True)


keep_alive()
bot.run(os.getenv("TOKEN"))
