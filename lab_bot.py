import re
import discord

import database as db


async def create_temp_channel(guild: discord.Guild, name: str, channel_type, category=None, position: int = None,
                              overwrites=None, parent_id=None):
    if channel_type == "voice":
        channel = await guild.create_voice_channel(name, category=category, position=position, overwrites=overwrites)
    else:
        channel = await guild.create_text_channel(name, category=category, position=position, overwrites=overwrites)

    if parent_id is None:
        db.update(db.temp_channel_ref(guild.id, channel.id), db.Key.related, [])
    else:
        db.append_array(db.temp_channel_ref(guild.id, parent_id), db.Key.related, channel.id)

    return channel


async def delete_temp_channel(guild: discord.Guild, channel_id: int):
    channel = guild.get_channel(channel_id)
    if channel is not None:
        await channel.delete()
    temp_ref = db.temp_channel_ref(guild.id, channel_id)
    if (temp := temp_ref.get()) is None:
        return
    try:
        related_channel_ids = temp.to_dict()[db.Key.related.name]
        for related_channel_id in related_channel_ids:
            related_channel = guild.get_channel(related_channel_id)
            if related_channel is not None:
                await related_channel.delete()
    except KeyError:
        pass
    temp_ref.delete()


def room_name(username: str):
    if username[-1] == "s":
        return f"{username}' Room"
    else:
        return f"{username}'s Room"


def queue_role_name(name: str):
    return f"{name.title()} Queue"


async def create_queue_role(guild: discord.Guild, queue_id: int):
    queue_name = db.get(db.queue_ref(guild.id, queue_id), db.Key.name)
    role = await guild.create_role(name=queue_role_name(queue_name), hoist=True)

    for queue_channel in db.queues_ref(guild.id).stream():
        channel = guild.get_channel(int(queue_channel.id))
        await channel.set_permissions(role, connect=False)

    return role


async def new_queue(ctx, name: str):
    channel = await ctx.guild.create_voice_channel(f"➕ Join {name} queue...")
    db.update(db.queue_ref(ctx.guild.id, channel.id), db.Key.name, name)
    await create_queue_role(ctx.guild, channel.id)


async def open_queue(ctx):
    for queue_channel in db.queues_ref(ctx.guild.id).stream():
        channel = ctx.guild.get_channel(int(queue_channel.id))
        await channel.set_permissions(ctx.guild.default_role, overwrite=None)
        await queue_update(ctx.guild, int(queue_channel.id))

    await delete_queue_status_message(ctx.guild)
    db.update(db.guild_ref(ctx.guild.id), db.Key.queue_status, True)
    message = await ctx.send(">>> :clipboard: __**Lab Queue**__\n*The queue is now open!*\n\nCreate a waiting "
                             "room to enter the queue.")
    await message.pin()
    db.update(db.guild_ref(ctx.guild.id), db.Key.queue_status_message, [ctx.channel.id, message.id])


async def close_queue(ctx):
    for queue_channel in db.queues_ref(ctx.guild.id).stream():
        channel = ctx.guild.get_channel(int(queue_channel.id))
        await channel.set_permissions(ctx.guild.default_role, connect=False)

    await delete_queue_status_message(ctx.guild)
    db.update(db.guild_ref(ctx.guild.id), db.Key.queue_status, False)
    message = await ctx.send(">>> :x: __**Lab Queue**__\n*The queue is now closed.*\n\n"
                             "Come back next time to get signed off :slight_smile:")
    await message.pin()
    db.update(db.guild_ref(ctx.guild.id), db.Key.queue_status_message, [ctx.channel.id, message.id])


async def queue_update(guild: discord.Guild, queue_id: int):
    queue = db.get(db.queue_ref(guild.id, queue_id), db.Key.queue, default=[])
    queue_name = db.get(db.queue_ref(guild.id, queue_id), db.Key.name, default="Lab")
    queue_update_channel = guild.get_channel(db.get(db.guild_ref(guild.id), db.Key.queue_updates_channel))

    await delete_queue_update_message(guild, queue_id)

    if len(queue) > 0:
        regex = re.compile(r" \(\d+\)")
        user = await guild.fetch_member(queue[0])
        message = await queue_update_channel.send(f">>> :stopwatch: __**{queue_name.title()} Queue**__\n*"
                                                  f"{regex.sub('', user.display_name)} is "
                                                  f"next in the queue.*\n\nTo move them to your room click ✅")
        await message.add_reaction("✅")

        for i in range(len(queue)):
            user = await guild.fetch_member(queue[i])
            await update_queue_position(user, i + 1, regex=regex)
    else:
        message = await queue_update_channel.send(f">>> :stopwatch: __**{queue_name.title()} Queue**__"
                                                  f"\n*The queue is empty.*")

    db.update(db.queue_ref(guild.id, queue_id), db.Key.queue_update_message, [queue_update_channel.id, message.id])


async def update_queue_position(user: discord.Member, position: int, regex=re.compile(r" \(\d+\)")):
    try:
        if position == 0:
            await user.edit(nick=f"{regex.sub('', user.display_name)}")
        else:
            await user.edit(nick=f"{regex.sub('', user.display_name)} ({position})")
    except discord.errors.Forbidden:
        pass


async def on_queue_message_react(reaction: discord.Reaction, user: discord.Member):
    queues = db.queues_ref(user.guild.id).where(db.Key.queue_update_message.name, "==",
                                                [reaction.message.channel.id, reaction.message.id]).stream()
    queue_id = None
    for queue in queues:
        queue_id = int(queue.id)
        break

    if queue_id is None:
        return

    if user.voice is None:
        await reaction.message.channel.send("❌ You must be in a voice channel!", delete_after=5)
        await reaction.remove(user)
    else:
        await reaction.message.delete()
        queue_ref = db.queue_ref(user.guild.id, queue_id)
        queue = db.get(queue_ref, db.Key.queue, default=[])
        db.remove_array(queue_ref, db.Key.queue, queue[0])

        user_waiting = await user.guild.fetch_member(queue[0])
        await user_waiting.edit(voice_channel=user.voice.channel)
        await update_queue_position(user_waiting, 0)
        await queue_update(user.guild, queue_id)

        related_channel_ids = db.get(db.temp_channel_ref(user.guild.id, user.voice.channel.id), db.Key.related, [])

        for related_channel_id in related_channel_ids:
            related_channel = user.guild.get_channel(related_channel_id)
            await related_channel.set_permissions(user_waiting, view_channel=True, send_messages=True)


async def delete_queue_status_message(guild: discord.Guild):
    old_message = db.get(db.guild_ref(guild.id), db.Key.queue_status_message, [0, 0])
    channel = guild.get_channel(old_message[0])
    if channel is not None:
        try:
            await delete_message(await channel.fetch_message(old_message[1]))
        except discord.errors.NotFound:
            pass


async def delete_queue_update_message(guild: discord.Guild, queue_id: int):
    old_message = db.get(db.queue_ref(guild.id, queue_id), db.Key.queue_update_message, [0, 0])
    channel = guild.get_channel(old_message[0])
    if channel is not None:
        try:
            await delete_message(await channel.fetch_message(old_message[1]))
        except discord.errors.NotFound:
            pass


async def delete_message(message: discord.Message):
    if message is not None:
        await message.delete()
