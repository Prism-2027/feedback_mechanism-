import hashlib
import json
import unittest
from pathlib import Path

from feedback_mechanism import merge_feedback


def make_feedback(**overrides):
    feedback = {
        "feedback_id": "FB_001",
        "user_id": "USER_001",
        "snapshot_id": "SIT_001",
        "ts": 1795000000,
        "context": {
            "situation_type": "communication",
            "situation_subtype": "incoming_call",
            "trigger_summary": "Repeated incoming calls from Rahul",
        },
        "executed": {
            "action_type": "send_message",
            "channel": "whatsapp",
            "tone": "warm",
            "timing": "now",
        },
        "response": {
            "outcome": "accepted",
            "latency_ms": 1000,
            "user_action": "sent_reassuring_message",
        },
        "prediction": {"top": "send_message", "confidence": 0.8},
        "counterpart": "PERSON_001",
        "stakes": "high",
    }
    feedback.update(overrides)
    return feedback


class FeedbackMechanismTests(unittest.TestCase):
    def test_merges_repository_feedback_and_schema_examples(self):
        root = Path(__file__).resolve().parents[1]
        episodic = json.loads((root / "schemas/Episodic_memory_Sample.json").read_text())
        relationship = json.loads((root / "schemas/relationship_memory_sample.json").read_text())
        value = json.loads((root / "schemas/value_memory_sample.json").read_text())
        memory = {
            "episodic_memory": [episodic],
            "relationship_memory": [relationship],
            "value_model": [value],
        }
        feedback = {
            "feedback_id": "FB_REPO_INTEGRATION",
            "user_id": "USER_DEMO_014",
            "snapshot_id": "SIT_014",
            "ts": 1795000000,
            "context": {
                "situation_type": "schedule",
                "situation_subtype": "calendar_reminder",
                "trigger_summary": "A project check-in is scheduled to begin shortly",
            },
            "executed": {
                "action_type": "show_meeting_brief",
                "channel": "calendar",
                "tone": "concise",
                "timing": "before_meeting",
            },
            "response": {
                "outcome": "accepted",
                "user_action": "show_meeting_brief",
                "user_feedback_score": 5,
            },
            "counterpart": "PERSON_DEMO_014",
        }

        merged = merge_feedback(feedback, memory)

        self.assertEqual(relationship["_id"], merged["relationship_memory"][0]["_id"])
        self.assertEqual(value["_id"], merged["value_model"][0]["_id"])
        episode_ids = merged["relationship_memory"][0]["tie_state"]["evidence_ids"]
        self.assertIn("EP_FB_REPO_INTEGRATION", episode_ids)
        episode = next(
            item for item in merged["episodic_memory"]
            if item["_id"] == "EP_FB_REPO_INTEGRATION"
        )
        self.assertEqual(
            episode["decision_and_outcome"]["evaluation"]["user_feedback_score"],
            5,
        )

    def test_merge_records_episode_and_updates_all_memory_stores(self):
        memory = {"episodic_memory": [], "relationship_memory": [], "value_model": []}

        merged = merge_feedback(make_feedback(), memory)

        self.assertEqual(len(merged["episodic_memory"]), 1)
        episode = merged["episodic_memory"][0]
        self.assertFalse(episode["outcome"]["prediction_matched"])
        self.assertEqual(episode["outcome"]["actual_user_action"], "sent_reassuring_message")
        self.assertEqual(episode["decision_and_outcome"]["evaluation"]["user_feedback_score"], 5)
        self.assertEqual(episode["decision_and_outcome"]["evaluation"]["emotional_valence"], "positive")
        relationship = merged["relationship_memory"][0]
        self.assertEqual(relationship["tie_state"]["evidence_ids"], ["EP_FB_001"])
        value = next(item for item in merged["value_model"] if item["value_name"].endswith("Channel Preference"))
        self.assertEqual(value["behavioral_preference"]["preferred_action"], "whatsapp")
        self.assertEqual(value["provenance"]["supporting_episodes"], ["EP_FB_001"])
        self.assertEqual(memory, {"episodic_memory": [], "relationship_memory": [], "value_model": []})

    def test_merge_is_idempotent_and_preserves_stated_hard_rules(self):
        feedback = make_feedback()
        value_id = "VAL_" + hashlib.sha256(b"USER_001|channel").hexdigest()[:20].upper()
        existing_value = {
            "_id": value_id,
            "user_id": "USER_001",
            "category": "hard_rule",
            "provenance": {"source": "stated"},
            "behavioral_preference": {"preferred_action": "phone"},
        }
        memory = {
            "episodic_memory": [],
            "relationship_memory": [],
            "value_model": [existing_value],
        }
        first = merge_feedback(feedback, memory)
        second = merge_feedback(feedback, first)

        self.assertEqual(second, first)
        self.assertEqual(first["value_model"][0], existing_value)

    def test_conflicting_feedback_is_recorded_without_replacing_preference(self):
        value_id = "VAL_" + hashlib.sha256(b"USER_001|channel").hexdigest()[:20].upper()
        existing_value = {
            "_id": value_id,
            "user_id": "USER_001",
            "category": "preference",
            "behavioral_preference": {"preferred_action": "phone"},
            "provenance": {
                "source": "inferred",
                "supporting_episodes": ["EP_OLD"],
                "contradicting_episodes": [],
            },
            "validation": {
                "status": "provisional",
                "needs_user_confirmation": True,
                "contradiction_count": 0,
            },
        }
        memory = {
            "episodic_memory": [],
            "relationship_memory": [],
            "value_model": [existing_value],
        }

        merged = merge_feedback(make_feedback(), memory)

        value = merged["value_model"][0]
        self.assertEqual(value["behavioral_preference"]["preferred_action"], "phone")
        self.assertEqual(value["provenance"]["contradicting_episodes"], ["EP_FB_001"])
        self.assertEqual(value["validation"]["status"], "conflicting")

    def test_updates_original_relationship_and_soft_value_with_reference_formulas(self):
        relationship = {
            "_id": "REL_USER_001_PERSON_001",
            "user_id": "USER_001",
            "person_id": "PERSON_001",
            "identity": {"name": "Rahul", "role": "close_friend"},
            "interaction_stats": {
                "total_interactions": 120,
                "calls_count": 35,
                "messages_count": 75,
                "meetings_count": 10,
                "average_interactions_per_week": 10.0,
                "average_response_time_minutes": 12,
                "user_initiation_ratio": 0.45,
                "other_person_initiation_ratio": 0.55,
                "calculation_period_days": 90,
            },
            "tie_state": {
                "recent_tension": False,
                "interaction_reciprocity": 0.9,
                "source": "inferred",
                "evidence_ids": [],
            },
            "scores": {
                "closeness": {"value": 0.9, "source": "inferred", "confidence": 0.5, "evidence_ids": []},
                "trust": {"value": 0.8, "source": "inferred", "confidence": 0.5, "evidence_ids": []},
                "importance": {"value": 0.8, "source": "inferred", "confidence": 0.5, "evidence_ids": []},
            },
            "score_history": [],
            "metadata": {"schema_version": "2.0"},
        }
        value = {
            "_id": "VAL_003",
            "user_id": "USER_001",
            "value_name": "Reassurance in Close Relationships",
            "category": "soft_value",
            "domain": "communication",
            "statement": "The user prefers to reassure close friends rather than leave repeated calls unanswered.",
            "behavioral_preference": {
                "preferred_action": "Send a brief reassuring message and provide a callback time",
                "avoid_actions": ["Completely ignoring repeated calls"],
                "tone_guidance": "warm, brief, reassuring",
            },
            "priority_weight": 0.7,
            "conditions": {
                "applies_to_roles": ["close_friend"],
                "min_closeness": 0.8,
                "trigger": "repeated_incoming_calls",
            },
            "exceptions": ["driving", "in_exam", "sleeping"],
            "provenance": {
                "source": "inferred",
                "confidence": 0.58,
                "supporting_episodes": [],
                "contradicting_episodes": [],
            },
            "validation": {"status": "provisional", "needs_user_confirmation": True},
            "active": True,
        }
        prior_episode = {
            "_id": "EP_OLD",
            "user_id": "USER_001",
            "entities_involved": ["PERSON_001"],
            "decision_and_outcome": {
                "selected_action": {"action_type": "send_message"},
                "evaluation": {"emotional_valence": "positive", "user_feedback_score": 5},
            },
        }
        memory = {
            "episodic_memory": [prior_episode],
            "relationship_memory": [relationship],
            "value_model": [value],
        }

        merged = merge_feedback(make_feedback(), memory)

        updated_relationship = merged["relationship_memory"][0]
        self.assertEqual(updated_relationship["_id"], "REL_USER_001_PERSON_001")
        self.assertEqual(updated_relationship["interaction_stats"]["total_interactions"], 121)
        self.assertAlmostEqual(updated_relationship["tie_state"]["interaction_reciprocity"], 0.9)
        self.assertAlmostEqual(updated_relationship["scores"]["closeness"]["value"], 0.912)
        self.assertAlmostEqual(updated_relationship["scores"]["trust"]["value"], 0.836)
        self.assertAlmostEqual(updated_relationship["scores"]["importance"]["value"], 0.823)
        self.assertEqual(updated_relationship["scores"]["closeness"]["confidence"], 0.56)
        self.assertEqual(len(updated_relationship["score_history"]), 3)

        updated_value = next(item for item in merged["value_model"] if item["_id"] == "VAL_003")
        self.assertEqual(updated_value["provenance"]["supporting_episodes"], ["EP_FB_001"])
        self.assertEqual(updated_value["provenance"]["confidence"], 0.58)
        self.assertAlmostEqual(updated_value["priority_weight"], 0.92)
        self.assertEqual(updated_value["category"], "soft_value")

    def test_rejects_cross_user_memory(self):
        memory = {
            "episodic_memory": [],
            "relationship_memory": [],
            "value_model": [{"_id": "VAL_1", "user_id": "USER_002"}],
        }

        with self.assertRaisesRegex(ValueError, "different user_id"):
            merge_feedback(make_feedback(), memory)

    def test_rejects_feedback_scores_outside_one_to_five(self):
        feedback = make_feedback()
        feedback["response"]["user_feedback_score"] = 6
        memory = {"episodic_memory": [], "relationship_memory": [], "value_model": []}

        with self.assertRaisesRegex(ValueError, "user_feedback_score"):
            merge_feedback(feedback, memory)


if __name__ == "__main__":
    unittest.main()
