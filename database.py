import firebase_admin
from firebase_admin import credentials, firestore
from enum import Enum
from google.api_core.exceptions import NotFound

cred = credentials.Certificate("firebase.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
print("Connected to the database...")


class Collection(Enum):
    guilds = "guilds"
    temp_channels = "temp_channels"
    queues = "queues"


class Key(Enum):
    related = "related"
    queue = "queue"
    queue_status = "queue_status"
    queue_updates_channel = "queue_updates_channel"
    queue_status_message = "queue_status_message"
    queue_update_message = "queue_update_message"
    assistant_room_chats_category = "assistant_room_chats_category"
    create_assistant_room_channel = "create_assistant_room_channel"


def get(ref: firestore.firestore.DocumentReference, key: Key, default=None):
    guild = ref.get()

    if guild.exists:
        return guild.to_dict()[key.name]
    else:
        return default


def update(ref: firestore.firestore.DocumentReference, key: Key, value):
    ref.set({key.name: value}, merge=True)


def append_array(ref: firestore.firestore.DocumentReference, key: Key, value):
    try:
        ref.update({key.name: firestore.firestore.ArrayUnion([value])})
    except NotFound:
        update(ref, key, [])
        ref.update({key.name: firestore.firestore.ArrayUnion([value])})


def remove_array(ref: firestore.firestore.DocumentReference, key: Key, value):
    try:
        ref.update({key.name: firestore.firestore.ArrayRemove([value])})
    except NotFound:
        update(ref, key, [])
        ref.update({key.name: firestore.firestore.ArrayRemove([value])})


def guild_ref(guild_id: int) -> firestore.firestore.DocumentReference:
    return db.collection(Collection.guilds.name).document(str(guild_id))


def temp_channel_ref(guild_id: int, channel_id: int) -> firestore.firestore.DocumentReference:
    return db.collection(Collection.guilds.name).document(str(guild_id)) \
        .collection(Collection.temp_channels.name).document(str(channel_id))


def temp_channels_ref(guild_id: int) -> firestore.firestore.CollectionReference:
    return db.collection(Collection.guilds.name).document(str(guild_id)) \
        .collection(Collection.temp_channels.name)


def queue_ref(guild_id: int, queue_id: int) -> firestore.firestore.DocumentReference:
    return db.collection(Collection.guilds.name).document(str(guild_id)) \
        .collection(Collection.queues.name).document(str(queue_id))


def queues_ref(guild_id: int) -> firestore.firestore.CollectionReference:
    return db.collection(Collection.guilds.name).document(str(guild_id)) \
        .collection(Collection.queues.name)
