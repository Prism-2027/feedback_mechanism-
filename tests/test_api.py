import unittest

from fastapi.testclient import TestClient

from api import app


class FeedbackApiTests(unittest.TestCase):
    def test_merge_endpoint_returns_updated_memory_bundle(self):
        client = TestClient(app)
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

    def test_merge_endpoint_validates_feedback_contract(self):
        client = TestClient(app)
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
