"""MongoDB persistence for Persona Memory collections."""

import json
import os
from typing import Any

from pymongo import MongoClient


COLLECTIONS = ("episodic_memory", "relationship_memory", "value_model")


class MongoPersonaMemoryStore:
    def __init__(
        self,
        uri: str | None = None,
        database_name: str | None = None,
    ) -> None:
        self.client = MongoClient(
            uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
            serverSelectionTimeoutMS=5000,
        )
        self.database = self.client[database_name or os.getenv("MONGODB_DATABASE", "persona_memory")]

    def ping(self) -> None:
        self.database.command("ping")

    def load(self, user_id: str) -> dict[str, list[dict[str, Any]]]:
        memory: dict[str, list[dict[str, Any]]] = {}
        for name in COLLECTIONS:
            documents = []
            for stored in self.database[name].find({"user_id": user_id}):
                document = dict(stored)
                document["_id"] = document.pop("persona_memory_id")
                documents.append(document)
            memory[name] = documents
        return memory

    def save(self, memory: dict[str, list[dict[str, Any]]]) -> None:
        for name in COLLECTIONS:
            for document in memory[name]:
                record_id = document.get("_id")
                user_id = document.get("user_id")
                if not isinstance(record_id, str) or not record_id:
                    raise ValueError(f"{name} documents must have a non-empty _id")
                if not isinstance(user_id, str) or not user_id:
                    raise ValueError(f"{name} documents must have a non-empty user_id")

                stored = dict(document)
                stored.pop("_id")
                stored["persona_memory_id"] = record_id
                stored["_id"] = json.dumps([user_id, record_id], separators=(",", ":"))
                self.database[name].replace_one(
                    {"_id": stored["_id"]},
                    stored,
                    upsert=True,
                )
