import firebase_admin
from firebase_admin import credentials, firestore


class Database:
    def __init__(self):
        cred = credentials.Certificate("firebase.json")
        firebase_admin.initialize_app(cred)
        self.db = firestore.client()
        print("Connected to the database...")

    def _guild_ref(self, guild_id):
        guild_ref = self.db.collection('guilds').document(str(guild_id))

        if not guild_ref.get().exists:
            guild_ref.set({
                "add_sign_off_channel": 0,
                "add_help_channel": 0,
                "queue_status": False,
                "queue_message": [0, 0],
                "temp_channels": [],
                "sign_off_queue": [],
                "help_queue": [],
            })

        return guild_ref

    def get(self, guild_id, key: str, default=None):
        guild = self._guild_ref(guild_id).get()

        if guild.exists:
            return guild.to_dict()[key]
        else:
            return default

    def set(self, guild_id, key: str, value):
        self._guild_ref(guild_id).set({
            key: value
        }, merge=True)

    def append_array(self, guild_id, key: str, value):
        self._guild_ref(guild_id).update({key: firestore.ArrayUnion([value])})

    def remove_array(self, guild_id, key: str, value):
        self._guild_ref(guild_id).update({key: firestore.ArrayRemove([value])})
    

db = Database()
