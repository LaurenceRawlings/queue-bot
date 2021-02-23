import os
import discord
from discord.ext import commands
from discord import MessageType
from discord.ext.commands import has_role, MissingPermissions
from discord.ext.commands.errors import MissingRole
from discord_slash import SlashCommand, SlashContext
from discord_slash.utils import manage_commands
from dotenv import load_dotenv

import queue_bot as bot
import database as db
from keep_alive import keep_alive

load_dotenv()

client = commands.Bot(command_prefix="!")
slash = SlashCommand(client, sync_commands=True)
guild_ids = [int(guild) for guild in os.getenv("GUILD_IDS").split(",")]


def main():
    keep_alive()
    client.run(os.getenv("TOKEN"))


async def response(ctx, message):
    await ctx.send(message, hidden=True)


def error_message(message):
    return f"❌ {message}"


def info_message(message):
    return f"ℹ️ {message}"


@client.event
async def on_ready():
    print(f"{client.user} has come online...")


@client.event
async def on_message(message):
    if message.type == MessageType.pins_add and message.author.bot:
        try:
            await message.delete()
        except discord.errors.NotFound:
            pass


@client.event
async def on_slash_command_error(ctx, error):
    await ctx.respond(eat=True)
    if isinstance(error, MissingPermissions):
        await response(ctx, error_message("You are missing the required permissions to run this command."))
    elif isinstance(error, MissingRole):
        await response(ctx, error_message("You are missing the required roles to run this command."))
    else:
        raise error


@client.event
async def on_reaction_add(reaction, user):
    if [reaction.message.channel.id, reaction.message.id] in \
            [queue.to_dict()[db.Key.queue_update_message.name] for queue in db.queues_ref(user.guild.id).stream()]:
        if user == client:
            return
        if reaction.emoji != "✅":
            await reaction.remove(user)
            return
        await bot.on_queue_message_react(reaction, user)


@client.event
async def on_voice_state_update(ctx, before, after):
    new_channel = after.channel
    old_channel = before.channel

    if new_channel is not None:
        create_assistant_room_channel_id = db.get(db.guild_ref(ctx.guild.id), db.Key.create_assistant_room_channel)
        create_waiting_room_channel_ids = [int(channel.id) for channel in db.queues_ref(ctx.guild.id).stream()]

        if new_channel.id in create_waiting_room_channel_ids + [create_assistant_room_channel_id]:
            room_name = bot.room_name(ctx.display_name)
            temp_channel = await bot.create_temp_channel(ctx.guild, room_name, "voice",
                                                         new_channel.category)

            await ctx.edit(voice_channel=temp_channel)

            if new_channel.id == create_assistant_room_channel_id:
                category_id = db.get(db.guild_ref(ctx.guild.id), db.Key.assistant_room_chats_category)
                category = discord.utils.get(ctx.guild.categories, id=category_id)
                await bot.create_temp_channel(ctx.guild, room_name, "text", category=category,
                                              parent_id=temp_channel.id)
            elif new_channel.id in create_waiting_room_channel_ids:
                queue_name = db.get(db.queue_ref(ctx.guild.id, new_channel.id), db.Key.name, default="")
                role = discord.utils.get(ctx.guild.roles, name=bot.queue_role_name(queue_name))
                if role is None:
                    role = await bot.create_queue_role(ctx.guild, new_channel.id)
                await ctx.add_roles(role)
                db.append_array(db.queue_ref(ctx.guild.id, new_channel.id), db.Key.queue, ctx.id)
                queue = db.get(db.queue_ref(ctx.guild.id, new_channel.id), db.Key.queue, default=[])
                if len(queue) == 1:
                    await bot.queue_update(ctx.guild, new_channel.id)
                else:
                    await bot.update_queue_position(ctx, len(queue))

    else:
        queues = db.queues_ref(ctx.guild.id).where(db.Key.queue.name, "array_contains", ctx.id).stream()

        for queue in queues:
            db.remove_array(db.queue_ref(ctx.guild.id, int(queue.id)), db.Key.queue, ctx.id)

            queue_list = queue.to_dict()[db.Key.queue.name]
            await bot.update_queue_position(ctx, 0)
            if len(queue_list) > 0 and queue_list[0] == ctx.id:
                await bot.queue_update(ctx.guild, int(queue.id))

            role_name = bot.queue_role_name(queue.to_dict()[db.Key.name.name])
            role = discord.utils.get(ctx.guild.roles, name=role_name)
            if role is not None:
                await ctx.remove_roles(role)

    if old_channel is not None:
        temp_channel_ids = [int(temp_channel.id) for temp_channel in db.temp_channels_ref(ctx.guild.id).stream()]
        if old_channel.id in temp_channel_ids:
            if len(old_channel.members) == 0:
                await bot.delete_temp_channel(ctx.guild, old_channel.id)
            else:
                related_channel_ids = db.get(db.temp_channel_ref(ctx.guild.id, old_channel.id), db.Key.related, [])
                for related_channel_id in related_channel_ids:
                    related_channel = ctx.guild.get_channel(related_channel_id)
                    await related_channel.set_permissions(ctx, overwrite=None)

                    if isinstance(related_channel, discord.TextChannel):
                        await related_channel.purge(limit=100)


@slash.slash(name="open",
             description="Opens all queues",
             guild_ids=guild_ids)
@has_role("Lab Assistant")
async def _queue(ctx: SlashContext):
    await ctx.respond(eat=True)
    await bot.open_queue(ctx)


@slash.slash(name="close",
             description="Closes all queues",
             guild_ids=guild_ids)
@has_role("Lab Assistant")
async def _queue(ctx: SlashContext):
    await ctx.respond(eat=True)
    await bot.close_queue(ctx)


@slash.slash(name="set",
             description="Set options for LabBot",
             options=[manage_commands.create_option(
                 name="create_assistant_room_channel",
                 description="Set the voice channel for creating an assistant room",
                 option_type=7,
                 required=False),

                 manage_commands.create_option(
                     name="assistant_room_chats_category",
                     description="Set the category for assistant room chats",
                     option_type=7,
                     required=False),

                 manage_commands.create_option(
                     name="queue_updates_channel",
                     description="Set the channel for queue updates",
                     option_type=7,
                     required=False)
             ],
             guild_ids=guild_ids)
@has_role("Admin")
async def _set(ctx: SlashContext, create_assistant_room_channel=None, assistant_room_chats_category=None,
               queue_updates_channel=None):
    await ctx.respond(eat=True)

    message = ""

    if create_assistant_room_channel is not None:
        if isinstance(create_assistant_room_channel, discord.channel.VoiceChannel):
            db.update(db.guild_ref(ctx.guild.id), db.Key.create_assistant_room_channel,
                      create_assistant_room_channel.id)
            message += info_message("Create assistant room channel changed successfully!\n")
        else:
            message += error_message("The assistant room channel must be a voice channel.\n")
    if assistant_room_chats_category is not None:
        if isinstance(assistant_room_chats_category, discord.channel.CategoryChannel):
            db.update(db.guild_ref(ctx.guild.id), db.Key.assistant_room_chats_category,
                      assistant_room_chats_category.id)
            message += info_message("Assistant room chats category changed successfully!\n")
        else:
            message += error_message("The assistant room chats category must be a category.\n")
    if queue_updates_channel is not None:
        if isinstance(queue_updates_channel, discord.channel.TextChannel):
            db.update(db.guild_ref(ctx.guild.id), db.Key.queue_updates_channel, queue_updates_channel.id)
            message += info_message("Queue updates channel changed successfully!\n")
        else:
            message += error_message("The queue updates channel must be a text channel.\n")

    if len(message) > 0:
        await response(ctx, message)


@slash.slash(name="new",
             description="Create a new queue",
             options=[manage_commands.create_option(
                 name="name",
                 description="The name for the new queue",
                 option_type=3,
                 required=True)],
             guild_ids=guild_ids)
@has_role("Admin")
async def _set(ctx: SlashContext, name: str):
    await bot.new_queue(ctx, name)
    await response(ctx, info_message("New queue created successfully!"))


if __name__ == "__main__":
    main()
