import discord
import os
import re
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
async def on_reaction_add(reaction, user):
    if reaction.message.id == db.get(user.guild.id, "queue_update_message", [0, 0])[1]:
        if user == bot: return
        if reaction.emoji != "✅":
            await reaction.remove(user)
            return
        if user.voice == None:
            await reaction.message.channel.send("❌ You must be in a voice channel!", delete_after=5)
            await reaction.remove(user)
        else:
            queue = db.get(user.guild.id, "sign_off_queue", default=[])
            await reaction.message.delete()
            db.remove_array(user.guild.id, "sign_off_queue", queue[0])
            user_waiting = await user.guild.fetch_member(queue[0])
            await user_waiting.edit(voice_channel=user.voice.channel)
            await update_queue_position(user_waiting, 0)
            await queue_update(user.guild)


@bot.event
async def on_voice_state_update(ctx, before, after):
    create_room_channel_id = db.get(ctx.guild.id, "create_room_channel")
    create_waiting_room_channel_id = db.get(ctx.guild.id, "create_waiting_room_channel")

    new_channel = after.channel
    old_channel = before.channel

    if new_channel is not None:
        if new_channel.id in [create_room_channel_id, create_waiting_room_channel_id]:
            temp_channel = await create_temp_channel(ctx.guild, room_name(ctx.display_name), "voice", new_channel.category)
            await ctx.edit(voice_channel=temp_channel)

            if new_channel.id == create_room_channel_id: 
                category_id = db.get(ctx.guild.id, "room_chats_category")
                category = discord.utils.get(ctx.guild.categories, id=category_id)
                await create_temp_channel(ctx.guild, room_name(ctx.display_name), "text", category=category, parent_id=temp_channel.id)
            elif new_channel.id == create_waiting_room_channel_id:
                db.append_array(ctx.guild.id, "sign_off_queue", ctx.id)
                queue = db.get(ctx.guild.id, "sign_off_queue", default=[])
                if len(queue) == 1:
                    await queue_update(ctx.guild)
                else:
                    await update_queue_position(ctx, len(queue))
    else:
        queue = (db.get(ctx.guild.id, "sign_off_queue", default=[]))
        db.remove_array(ctx.guild.id, "sign_off_queue", ctx.id)
        await update_queue_position(ctx, 0)
        if len(queue) > 0 and queue[0] == ctx.id:
            await queue_update(ctx.guild)


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
                 name="create_room_channel",
                 description="Set the voice channel for creating a room",
                 option_type=7,
                 required=False),

                 manage_commands.create_option(
                 name="create_waiting_room_channel",
                 description="Set the voice channel for creating waiting rooms",
                 option_type=7,
                 required=False),

                 manage_commands.create_option(
                 name="room_chats_category",
                 description="Set the category for room chats",
                 option_type=7,
                 required=False),

                 manage_commands.create_option(
                 name="queue_channel",
                 description="Set the channel for queue updates",
                 option_type=7,
                 required=False)
             ],
             guild_ids=guild_ids)
@has_role("Admin")
async def _set(ctx: SlashContext, create_room_channel=None, create_waiting_room_channel=None, room_chats_category=None, queue_channel=None):
    await ctx.respond(eat=True)
    # TODO: sign off and help channels can't be the same
    if create_room_channel is not None:
        if isinstance(create_room_channel, discord.channel.VoiceChannel):
            db.set(ctx.guild.id, "create_room_channel", create_room_channel.id)
            await send_info(ctx, "Create room channel changed successfully!")
        else:
            await send_error(ctx, "The channel must be a voice channel.")
    if create_waiting_room_channel is not None:
        if isinstance(create_waiting_room_channel, discord.channel.VoiceChannel):
            db.set(ctx.guild.id, "create_waiting_room_channel", create_waiting_room_channel.id)
            await send_info(ctx, "Create waiting room channel changed successfully!")
        else:
            await send_error(ctx, "The channel must be a voice channel.")
    if room_chats_category is not None:
        if isinstance(room_chats_category, discord.channel.CategoryChannel):
            db.set(ctx.guild.id, "room_chats_category", room_chats_category.id)
            await send_info(ctx, "Room chats category changed successfully!")
        else:
            await send_error(ctx, "The channel must be a category.")
    if queue_channel is not None:
        if isinstance(queue_channel, discord.channel.TextChannel):
            db.set(ctx.guild.id, "queue_channel", queue_channel.id)
            await send_info(ctx, "Queue channel changed successfully!")
        else:
            await send_error(ctx, "The channel must be a text channel.")


async def create_temp_channel(guild: discord.Guild, name: str, channel_type, category=None, position: int = None, overwrites=None, parent_id = None):
    from firebase_admin import firestore

    if (channel_type == "voice"):
        channel = await guild.create_voice_channel(name, category=category, position=position, overwrites=overwrites)
    else:
        channel = await guild.create_text_channel(name, category=category, position=position, overwrites=overwrites)

    if parent_id is None:
        temp_ref = db.guild_ref(guild.id).collection("temp_channels").document(str(channel.id))
        temp_ref.set({"related": []})
    else:
        temp_ref = db.guild_ref(guild.id).collection("temp_channels").document(str(parent_id))
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
    db.set(ctx.guild.id, "queue_status", True)
    await ctx.respond(eat=True)
    await delete_queue_message(ctx.guild)
    message = await ctx.send(">>> :clipboard: __**Lab Queue**__\n*The queue is now open!*\n\nCreate or join a waiting room to enter the queue.")
    await message.pin()
    db.set(ctx.guild.id, "queue_message", [ctx.channel.id, message.id])
    waiting_room = ctx.guild.get_channel(db.get(ctx.guild.id, "create_waiting_room_channel"))
    await waiting_room.set_permissions(ctx.guild.default_role, overwrite=None)
    await queue_update(ctx.guild)


async def close_queue(ctx):
    db.set(ctx.guild.id, "queue_status", False)
    await ctx.respond(eat=True)
    message = await ctx.send(">>> :x: __**Lab Queue**__\n*The queue is now closed.*\n\nCome back next time to get signed off :slight_smile:")
    await delete_queue_message(ctx.guild)
    await message.pin()
    db.set(ctx.guild.id, "queue_message", [ctx.channel.id, message.id])
    waiting_room = ctx.guild.get_channel(db.get(ctx.guild.id, "create_waiting_room_channel"))
    await waiting_room.set_permissions(ctx.guild.default_role, view_channel=False)
    await delete_queue_update_message(ctx.guild)


async def queue_update(guild: discord.Guild):
    queue = db.get(guild.id, "sign_off_queue", default=[])
    queue_channel = guild.get_channel(db.get(guild.id, "queue_channel"))

    await delete_queue_update_message(guild)

    if len(queue) > 0:
        regex = re.compile(r" \(\d+\)")
        user = await guild.fetch_member(queue[0])
        message = await queue_channel.send(f">>> :stopwatch: __**Lab Queue**__\n*{regex.sub('', user.display_name)} is next in the queue.*\n\nTo move them to your room click ✅")
        await message.add_reaction("✅")

        for i in range(len(queue)):
            user = await guild.fetch_member(queue[i])
            await update_queue_position(user, i + 1, regex=regex)
    else:
        message = await queue_channel.send(">>> :stopwatch: __**Lab Queue**__\n*The queue is empty.*")

    db.set(guild.id, "queue_update_message", [queue_channel.id, message.id])


async def update_queue_position(user, position: int, regex=re.compile(r" \(\d+\)")):
    try:
        if position == 0:
            await user.edit(nick=f"{regex.sub('', user.display_name)}")
        else:
            await user.edit(nick=f"{regex.sub('', user.display_name)} ({position})")
    except:
        pass


async def delete_queue_message(guild: discord.guild):
    try:
        if old_message := db.get(guild.id, "queue_message", [0, 0]):
            await bot.http.delete_message(old_message[0], old_message[1])
    except:
        pass


async def delete_queue_update_message(guild: discord.guild):
    try:
        if old_message := db.get(guild.id, "queue_update_message", [0, 0]):
            await bot.http.delete_message(old_message[0], old_message[1])
    except:
        pass


async def send_error(ctx, message):
    await ctx.send(f"❌ {message}", hidden=True)


async def send_info(ctx, message):
    await ctx.send(f"ℹ️ {message}", hidden=True)


keep_alive()
bot.run(os.getenv("TOKEN"))
