# ![Logo](media/icon.png) QueueBot

Discord bot that puts users in a queue to wait for a designated assistant. Users wait in voice channels and then are
moved into a private assistant room when they are ready to be seen.

## How it works

*To run the slash commands, users must be given the `QueueAdmin` role!*

1. Assistants join the `Create room` voice channel to generate their voice channel, along with an accompanying text
   channel which can be used to send links etc. The assistant is automatically moved into their new voice channel when
   it is created.

2. Run the `/open` to open the queues. This will unlock the `Join queue` voice channels allowing users to connect and
   join the respective queue. Once a user has connected they will be moved into their new waiting room. From here the
   user is free to move into any other voice channel in the server, for example move to their friends waiting room to
   chat while they wait. If a user disconnects from the server they will automatically be removed from the queue.

3. Assistants will receive updates for each queue in the `queue` text channel. Updates will show user at the front of
   each queue and assistants can accept that user into their room by reacting with ✅. Once accepted that user will be
   removed from the queue.

4. The user and assistant can now chat in the voice channel. Also, the user will be given access to the assistants text
   chat.

5. Once finished the user can disconnect, and the assistant can accept the next person in the queue. Once disconnected
   the user will no longer have access to the assistants text chat and any messages that were sent in their session will
   be removed.

6. Finally, the queues can be closed with `/close` which will lock the voice channels for joining queues, however anyone
   still in a queue will remain.

## Features

- Simple interactions
- Multiple queues
- Temporary text channels for assistant rooms
- Open/Close queues
- Automated channel generation
- Automated user moving and queue management

## Demo

[![QueueBot Demo](media/demo.gif)](media/demo.mp4)

## Start using QueueBot!

### [Invite QueueBot](https://discord.com/api/oauth2/authorize?client_id=812345033856122930&permissions=469986384&scope=bot%20applications.commands)

Click the link above and review the permissions, note that QueueBot requires all listed permissions and will not work
correctly without them. Once QueueBot is in your server run the `/set` command to set up the required variables. Then
create your queues with `/new`.

### [Server Template](https://discord.new/Q2KdRzKuZjk2)

Use the above link to create a new Discord server with all the channels and permissions pre-configured. Just remember to
use the `/set` command to map your channels.

## Setup

Here are the slash commands that are essential for using QueueBot:

### /set

Map your server channels that QueueBot should use with `/set <parameter>:<value>`. Discord will help you will out the
rest, you can set multiple parameters at once. Here are the required parameters that need to be set:

| Parameter                     | Description                                          | Requirement   |
|-------------------------------|------------------------------------------------------|---------------|
| create_assistant_room_channel | Set the voice channel for creating an assistant room | Voice Channel |
| assistant_room_chats_category | Set the category for assistant room chats            | Category      |
| queue_updates_channel         | Set the channel for queue updates                    | Text Channel  |

### /new

Use the `/new name:<queue name>` command to create new queues. This will create new voice channels that act as entry
points to the queues. Once created these can be moved to any position in your server.

| Parameter | Description                | Requirement |
|-----------|----------------------------|-------------|
| Name      | The name for the new queue | String      |

To delete a queue, simply just delete the voice channel.

### /open and /close

The `/open` and `/close` commands unlock and lock the queue entry voice channels respectively. The bot will also respond
with an announcement message which gets pinned. It is best to use this command in a channel that can be viewed by
everyone.