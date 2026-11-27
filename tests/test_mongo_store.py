import copy
import unittest
from unittest.mock import patch

from mongo_store import COLLECTIONS, MongoPersonaMemoryStore


class CollectionFake:
    def __init__(self):
        self.documents = {}

    def find(self, query):
        return [
            copy.deepcopy(document)
            for document in self.documents.values()
            if document.get("user_id") == query["user_id"]
        ]

    def replace_one(self, query, document, upsert):
        self.documents[query["_id"]] = copy.deepcopy(document)


class DatabaseFake(dict):
    def __getitem__(self, name):
        if name not in self:
            self[name] = CollectionFake()
        return super().__getitem__(name)


class ClientFake(dict):
    def __getitem__(self, name):
        if name not in self:
            self[name] = DatabaseFake()
        return super().__getitem__(name)


class MongoPersonaMemoryStoreTests(unittest.TestCase):
    def test_round_trip_preserves_persona_ids_and_scopes_users(self):
        client = ClientFake()
        with patch("mongo_store.MongoClient", return_value=client):
            store = MongoPersonaMemoryStore("mongodb://example", "test")
            for user_id in ("USER_A", "USER_B"):
                store.save({
                    name: [{
                        "_id": "EP_SHARED",
                        "user_id": user_id,
                    }] if name == "episodic_memory" else []
                    for name in COLLECTIONS
                })

            memory_a = store.load("USER_A")
            memory_b = store.load("USER_B")

        self.assertEqual(memory_a["episodic_memory"], [{"_id": "EP_SHARED", "user_id": "USER_A"}])
        self.assertEqual(memory_b["episodic_memory"], [{"_id": "EP_SHARED", "user_id": "USER_B"}])
        self.assertEqual(memory_a["relationship_memory"], [])
        self.assertEqual(memory_a["value_model"], [])


if __name__ == "__main__":
    unittest.main()
