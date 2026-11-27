import copy
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api import app


class MemoryStoreFake:
    def __init__(self):
        self.memory = {
            "episodic_memory": [],
            "relationship_memory": [],
            "value_model": [],
        }

    def ping(self):
        return None

    def load(self, user_id):
        return {
            name: [item for item in copy.deepcopy(items) if item["user_id"] == user_id]
            for name, items in self.memory.items()
        }

    def save(self, memory):
        self.memory = copy.deepcopy(memory)


class FeedbackApiTests(unittest.TestCase):
    def test_merge_endpoint_returns_updated_memory_bundle(self):
        store = MemoryStoreFake()
        client = TestClient(app)
        with patch("api.get_memory_store", return_value=store):
            response = client.post(
                "/feedback/merge",
                json={
                    "feedback": {
                        "feedback_id": "FB_API_001",
                        "user_id": "USER_API",
                        "snapshot_id": "SIT_API",
                        "ts": 1795000000,
                        "executed": {"action_type": "send_message", "channel": "sms"},
                        "response": {
                            "outcome": "accepted",
                            "user_action": "sent_message",
                            "user_feedback_score": 4,
                        },
                    },
                    "persona_memory": {
                        "episodic_memory": [],
                        "relationship_memory": [],
                        "value_model": [],
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["episodic_memory"][0]["_id"], "EP_FB_API_001")
        self.assertEqual(
            result["episodic_memory"][0]["decision_and_outcome"]["evaluation"]["user_feedback_score"],
            4,
        )
        self.assertTrue(result["value_model"])
        self.assertEqual(store.memory, result)

    def test_merge_endpoint_reads_existing_memory_from_store(self):
        store = MemoryStoreFake()
        store.memory["value_model"].append({
            "_id": "VAL_EXISTING",
            "user_id": "USER_API",
            "category": "hard_rule",
            "provenance": {"source": "stated"},
        })
        client = TestClient(app)
        with patch("api.get_memory_store", return_value=store):
            response = client.post(
                "/feedback/merge",
                json={
                    "feedback": {
                        "feedback_id": "FB_API_DB_READ",
                        "user_id": "USER_API",
                        "snapshot_id": "SIT_API",
                        "ts": 1795000000,
                        "executed": {"action_type": "send_message", "channel": "sms"},
                        "response": {"outcome": "accepted"},
                    }
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["value_model"][0]["_id"], "VAL_EXISTING")
        self.assertEqual(response.json()["episodic_memory"][0]["_id"], "EP_FB_API_DB_READ")

    def test_merge_endpoint_validates_feedback_contract(self):
        client = TestClient(app)
        with patch("api.get_memory_store", return_value=MemoryStoreFake()):
            response = client.post(
                "/feedback/merge",
                json={
                    "feedback": {"feedback_id": "invalid"},
                    "persona_memory": {},
                },
            )

        self.assertEqual(response.status_code, 422)

    def test_merge_endpoint_rejects_out_of_range_feedback_score(self):
        client = TestClient(app)
        with patch("api.get_memory_store", return_value=MemoryStoreFake()):
            response = client.post(
                "/feedback/merge",
                json={
                    "feedback": {
                        "feedback_id": "FB_API_BAD_SCORE",
                        "user_id": "USER_API",
                        "snapshot_id": "SIT_API",
                        "ts": 1795000000,
                        "executed": {"action_type": "send_message", "channel": "sms"},
                        "response": {"outcome": "accepted", "user_feedback_score": 6},
                    },
                    "persona_memory": {
                        "episodic_memory": [],
                        "relationship_memory": [],
                        "value_model": [],
                    },
                },
            )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
