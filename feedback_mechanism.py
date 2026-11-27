"""Merge Action Block feedback into the canonical Persona Memory JSON format."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VALUE_DIMENSIONS = ("action_type", "channel", "tone", "timing")
ROLE_PRIORS = {
    "parent": {"closeness": 0.95, "trust": 0.95, "importance": 1.0, "weight": 1.0},
    "sibling": {"closeness": 0.90, "trust": 0.90, "importance": 0.95, "weight": 0.90},
    "close_friend": {"closeness": 0.90, "trust": 0.85, "importance": 0.90, "weight": 0.85},
    "professor": {"closeness": 0.35, "trust": 0.75, "importance": 0.85, "weight": 0.85},
    "coworker": {"closeness": 0.50, "trust": 0.70, "importance": 0.75, "weight": 0.75},
    "friend": {"closeness": 0.70, "trust": 0.75, "importance": 0.70, "weight": 0.65},
    "unknown": {"closeness": 0.20, "trust": 0.30, "importance": 0.30, "weight": 0.30},
}
OUTCOME_FEEDBACK_SCORE = {
    "accepted": 5,
    "modified": 4,
    "ignored": 3,
    "dismissed": 2,
    "overridden": 1,
}
PASSIVE_ACTIONS = {"do_nothing", "defer_notification"}
STAKE_LEVELS = {"low", "medium", "high"}


def _unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def _timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return prefix + hashlib.sha256(raw).hexdigest()[:20].upper()


def _validate_feedback(feedback: dict[str, Any]) -> None:
    if not isinstance(feedback, dict):
        raise ValueError("feedback must be an object")
    required = ("feedback_id", "user_id", "snapshot_id", "ts", "executed", "response")
    missing = [key for key in required if key not in feedback]
    if missing:
        raise ValueError(f"Feedback is missing required fields: {', '.join(missing)}")
    if not isinstance(feedback["feedback_id"], str) or not feedback["feedback_id"]:
        raise ValueError("feedback_id must be a non-empty string")
    if not isinstance(feedback["user_id"], str) or not feedback["user_id"]:
        raise ValueError("user_id must be a non-empty string")
    if not isinstance(feedback["executed"], dict) or not isinstance(feedback["response"], dict):
        raise ValueError("executed and response must be objects")
    for field in ("action_type", "channel"):
        if not isinstance(feedback["executed"].get(field), str) or not feedback["executed"][field]:
            raise ValueError(f"executed.{field} must be a non-empty string")
    if feedback["response"].get("outcome") not in OUTCOME_FEEDBACK_SCORE:
        raise ValueError("response.outcome must be accepted, modified, ignored, dismissed, or overridden")
    response_score = feedback["response"].get("user_feedback_score")
    if response_score is not None:
        if (
            isinstance(response_score, bool)
            or not isinstance(response_score, int)
            or not 1 <= response_score <= 5
        ):
            raise ValueError("response.user_feedback_score must be between 1 and 5")
    rating = feedback.get("rating")
    if isinstance(rating, bool) or rating not in (None, -1, 0, 1):
        raise ValueError("rating must be -1, 0, 1, or null")
    prediction = feedback.get("prediction")
    if prediction is not None:
        if not isinstance(prediction, dict) or not isinstance(prediction.get("top"), str):
            raise ValueError("prediction must include a top action")
        confidence = prediction.get("confidence")
        if confidence is None or not 0 <= float(confidence) <= 1:
            raise ValueError("prediction.confidence must be between 0 and 1")
    stakes = feedback.get("stakes", "low")
    if stakes not in STAKE_LEVELS:
        raise ValueError("stakes must be low, medium, or high")
    try:
        _timestamp(float(feedback["ts"]))
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("ts must be a valid Unix timestamp") from error


def _feedback_score(feedback: dict[str, Any]) -> int:
    response_score = feedback["response"].get("user_feedback_score")
    if response_score is not None:
        return max(1, min(5, int(response_score)))
    rating = feedback.get("rating")
    if rating is not None:
        return int(rating) * 2 + 3
    return OUTCOME_FEEDBACK_SCORE[feedback["response"]["outcome"]]


def _emotional_valence(score: int) -> str:
    if score >= 4:
        return "positive"
    if score <= 2:
        return "negative"
    return "neutral"


def _episode(feedback: dict[str, Any], timestamp: str) -> dict[str, Any]:
    response = feedback["response"]
    executed = feedback["executed"]
    prediction = feedback.get("prediction") or {}
    actual_action = response.get("user_action") or response["outcome"]
    predicted_action = prediction.get("top")
    counterpart = feedback.get("counterpart")
    context = feedback.get("context") or {}
    episode_id = f"EP_{feedback['feedback_id']}"
    feedback_score = _feedback_score(feedback)
    valence = _emotional_valence(feedback_score)
    selected_action = {
        key: executed[key]
        for key in ("action_type", "channel", "tone", "timing")
        if executed.get(key) is not None
    }
    return {
        "_id": episode_id,
        "user_id": feedback["user_id"],
        "situation_id": feedback["snapshot_id"],
        "timestamp": timestamp,
        "entities_involved": [counterpart] if counterpart else [],
        "context_summary": {
            "situation_type": context.get("situation_type", "action_block"),
            "situation_subtype": context.get("situation_subtype", executed.get("action_type")),
            "user_activity": context.get("user_activity", context.get("calendar")),
            "stress_level": context.get("stress_level", context.get("stress")),
            "trigger_summary": context.get("trigger_summary", "Action Block feedback"),
        },
        "outcome": {
            "predicted_action": predicted_action,
            "action_score": round(float(prediction.get("confidence", 0.0)) * 100),
            "actual_user_action": actual_action,
            "prediction_matched": (
                predicted_action == response.get("user_action")
                if predicted_action is not None and response.get("user_action") is not None
                else None
            ),
            "user_rationale": None,
            "emotional_valence": valence,
            "user_feedback_score": feedback_score,
        },
        "decision_and_outcome": {
            "selected_action": selected_action,
            "evaluation": {
                "emotional_valence": valence,
                "user_feedback_score": feedback_score,
                "user_action": response.get("user_action"),
            },
        },
        "follow_up": {
            "required": False,
            "promised_action": None,
            "deadline": None,
            "status": "not_required",
            "completed_at": None,
        },
        "memory_impact": {
            "updated_collections": ["episodic_memory", "relationships", "value_model"]
            if counterpart
            else ["episodic_memory", "value_model"],
            "learning_note": "Action Block outcome recorded as evidence for future personalization.",
        },
        "tags": ["action_block", response["outcome"]],
    }


def _new_relationship(user_id: str, person_id: str, timestamp: str) -> dict[str, Any]:
    return {
        "_id": "REL_" + _stable_id("", user_id, person_id),
        "user_id": user_id,
        "person_id": person_id,
        "identity": {
            "name": person_id,
            "aliases": [],
            "role": "unknown",
            "contact_identifiers": [],
        },
        "scores": {
            "closeness": {
                "value": 0.5,
                "source": "inferred",
                "confidence": 0.3,
                "updated_at": timestamp,
                "evidence_ids": [],
            },
            "trust": {
                "value": 0.5,
                "source": "inferred",
                "confidence": 0.3,
                "updated_at": timestamp,
                "evidence_ids": [],
            },
            "importance": {
                "value": 0.5,
                "source": "inferred",
                "confidence": 0.3,
                "updated_at": timestamp,
                "evidence_ids": [],
            },
        },
        "tie_state": {
            "current_status": "active",
            "recent_tension": False,
            "relationship_trend": "stable",
            "support_balance": "unknown",
            "interaction_reciprocity": 0.5,
            "last_interaction_at": timestamp,
            "source": "inferred",
            "confidence": 0.3,
            "evidence_ids": [],
        },
        "interaction_stats": {
            "total_interactions": 0,
            "calls_count": 0,
            "messages_count": 0,
            "meetings_count": 0,
            "average_interactions_per_week": 0,
            "average_response_time_minutes": None,
            "user_initiation_ratio": None,
            "other_person_initiation_ratio": None,
            "calculation_period_days": 90,
            "updated_at": timestamp,
        },
        "communication_preferences": {
            "preferred_channels": [],
            "preferred_contact_times": [],
            "source": "inferred",
            "confidence": 0.0,
            "evidence_ids": [],
        },
        "behavioral_patterns": {
            "user_behavior": [],
            "other_person_behavior": [],
            "observed_since": timestamp[:10],
            "updated_at": timestamp,
        },
        "relationship_boundaries": {
            "known_boundaries": [],
            "sensitive_topics": [],
            "interaction_restrictions": [],
            "source": "unknown",
            "confidence": 0.0,
            "evidence_ids": [],
        },
        "shared_context": {
            "known_connections": [],
            "shared_activities": [],
            "common_interests": [],
            "significant_shared_events": [],
        },
        "score_history": [],
        "metadata": {
            "created_at": timestamp,
            "updated_at": timestamp,
            "last_verified_at": None,
            "schema_version": "2.0",
        },
    }


def _episode_signal(episode: dict[str, Any]) -> dict[str, Any]:
    decision = episode.get("decision_and_outcome", {})
    evaluation = decision.get("evaluation", {})
    action = decision.get("selected_action", {})
    outcome = episode.get("outcome", {})
    context = episode.get("context_summary", {})
    action_type = (
        action.get("action_type")
        or outcome.get("actual_user_action")
        or outcome.get("selected_action", {}).get("action_type")
        or context.get("situation_subtype")
        or ""
    )
    score = evaluation.get("user_feedback_score", outcome.get("user_feedback_score"))
    valence = evaluation.get("emotional_valence", outcome.get("emotional_valence"))
    return {
        "action_type": str(action_type).lower().replace("-", "_"),
        "score": float(score) if score is not None else None,
        "valence": valence if valence in {"positive", "neutral", "negative"} else "neutral",
    }


def _role_prior(role: str | None) -> dict[str, float]:
    return ROLE_PRIORS.get(str(role or "unknown").lower(), ROLE_PRIORS["unknown"])


def _relationship_metrics(
    relationship: dict[str, Any], episodes: list[dict[str, Any]]
) -> tuple[dict[str, float], dict[str, float]]:
    stats = relationship.get("interaction_stats", {})
    tie_state = relationship.get("tie_state", {})
    user_ratio = stats.get("user_initiation_ratio")
    other_ratio = stats.get("other_person_initiation_ratio")
    if user_ratio is not None and other_ratio is not None:
        reciprocity = _unit(1.0 - abs(float(user_ratio) - float(other_ratio)))
    else:
        reciprocity = _unit(float(tie_state.get("interaction_reciprocity", 0.5)))

    weekly_frequency = max(0.0, float(stats.get("average_interactions_per_week") or 0.0))
    frequency_signal = min(weekly_frequency / 10.0, 1.0)
    response_time = stats.get("average_response_time_minutes")
    response_signal = (
        0.5
        if response_time is None
        else 1.0 - min(max(float(response_time), 0.0) / 120.0, 1.0)
    )
    signals = [_episode_signal(episode) for episode in episodes]
    if signals:
        positive_rate = sum(signal["valence"] == "positive" for signal in signals) / len(signals)
        clean_rate = sum(signal["valence"] != "negative" for signal in signals) / len(signals)
        feedback_quality = sum(
            (signal["score"] / 5.0) if signal["score"] is not None else 0.5
            for signal in signals
        ) / len(signals)
        priority_rate = sum(
            signal["action_type"] not in PASSIVE_ACTIONS for signal in signals
        ) / len(signals)
    else:
        positive_rate = clean_rate = feedback_quality = 0.5
        priority_rate = 0.0

    role = relationship.get("identity", {}).get("role", "unknown")
    role_weight = _role_prior(role)["weight"]
    metrics = {
        "closeness": _unit(
            0.35 * frequency_signal
            + 0.25 * response_signal
            + 0.25 * positive_rate
            + 0.15 * reciprocity
        ),
        "trust": _unit(
            0.45 * feedback_quality
            + 0.35 * clean_rate
            + 0.20 * reciprocity
            - (0.15 if tie_state.get("recent_tension") else 0.0)
        ),
        "importance": _unit(
            0.40 * role_weight + 0.35 * priority_rate + 0.25 * response_signal
        ),
    }
    return metrics, {
        "frequency": frequency_signal,
        "response_speed": response_signal,
        "episodic_impact": positive_rate,
        "reciprocity": reciprocity,
        "feedback_quality": feedback_quality,
        "conflict_free_rate": clean_rate,
        "priority_action_rate": priority_rate,
    }


def _matching_episodes(
    memory: dict[str, Any], user_id: str, person_id: str
) -> list[dict[str, Any]]:
    return [
        episode
        for episode in memory["episodic_memory"]
        if episode.get("user_id") == user_id and person_id in episode.get("entities_involved", [])
    ]


def _merge_relationship(
    memory: dict[str, Any], feedback: dict[str, Any], episode_id: str, timestamp: str
) -> dict[str, Any] | None:
    person_id = feedback.get("counterpart")
    if not person_id:
        return None
    user_id = feedback["user_id"]
    person_id = str(person_id)
    relationships = [
        item
        for item in memory["relationship_memory"]
        if item.get("user_id") == user_id and str(item.get("person_id")) == person_id
    ]
    if len(relationships) > 1:
        raise ValueError(f"Multiple relationship records found for person_id {person_id}")
    relationship = relationships[0] if relationships else _new_relationship(user_id, person_id, timestamp)
    if not relationships:
        relationship["_id"] = f"REL_{user_id}_{person_id}"
        memory["relationship_memory"].append(relationship)

    stats = relationship.setdefault("interaction_stats", {})
    action_type = str(feedback["executed"]["action_type"]).lower().replace("-", "_")
    is_active = action_type not in PASSIVE_ACTIONS
    if is_active:
        period_days = max(1, int(stats.get("calculation_period_days") or 90))
        stats["total_interactions"] = int(stats.get("total_interactions", 0)) + 1
        weekly_count = float(stats.get("average_interactions_per_week") or 0.0) * period_days / 7.0
        stats["average_interactions_per_week"] = (weekly_count + 1.0) * 7.0 / period_days
        action_channel = str(feedback["executed"].get("channel") or "").lower()
        if "call" in action_type or "call" in action_channel:
            stats["calls_count"] = int(stats.get("calls_count", 0)) + 1
        elif any(token in action_type or token in action_channel for token in ("message", "sms", "email", "chat")):
            stats["messages_count"] = int(stats.get("messages_count", 0)) + 1
        elif "meeting" in action_type or "meeting" in action_channel:
            stats["meetings_count"] = int(stats.get("meetings_count", 0)) + 1
    stats["updated_at"] = timestamp

    episodes = _matching_episodes(memory, user_id, person_id)
    tie_state = relationship.setdefault("tie_state", {})
    new_signal = _episode_signal(episodes[-1])
    if new_signal["valence"] == "negative":
        tie_state["recent_tension"] = True
    elif new_signal["valence"] == "positive":
        tie_state["recent_tension"] = False

    metrics, components = _relationship_metrics(relationship, episodes)
    episode_ids = list(dict.fromkeys(item.get("_id") for item in episodes if item.get("_id")))
    confidence = min(0.50 + 0.03 * len(episodes), 0.95)
    history = relationship.setdefault("score_history", [])
    scores = relationship.setdefault("scores", {})
    for metric, target in metrics.items():
        score = scores.setdefault(metric, {})
        if score.get("source") == "stated":
            continue
        old_value = _unit(float(score.get("value", 0.5)))
        new_value = _unit(0.8 * old_value + 0.2 * target)
        score.update(
            value=new_value,
            source="inferred",
            confidence=confidence,
            updated_at=timestamp,
            evidence_ids=episode_ids,
        )
        history.append(
            {
                "metric": metric,
                "old_value": old_value,
                "new_value": new_value,
                "reason": (
                    f"EMA update from {len(episodes)} episodes "
                    f"(frequency={components['frequency']:.3f}, "
                    f"response={components['response_speed']:.3f}, "
                    f"episodic={components['episodic_impact']:.3f}, "
                    f"reciprocity={components['reciprocity']:.3f})"
                ),
                "evidence_ids": episode_ids,
                "timestamp": timestamp,
            }
        )

    existing_tie_source = tie_state.get("source")
    tie_state.update(
        interaction_reciprocity=components["reciprocity"],
        evidence_ids=episode_ids,
        last_interaction_at=timestamp,
    )
    if existing_tie_source != "stated":
        tie_state.update(source="inferred", confidence=confidence)
    relationship.setdefault("metadata", {})["updated_at"] = timestamp
    return relationship


def _tokens(value: Any) -> set[str]:
    words = re.findall(r"[a-z0-9]+", str(value).lower())
    normalized = []
    for word in words:
        word = {
            "sent": "send",
            "sending": "send",
            "messages": "message",
            "messaging": "message",
            "calls": "call",
            "called": "call",
            "reassured": "reassure",
            "reassuring": "reassure",
        }.get(word, word)
        normalized.append(word)
    return {word for word in normalized if word not in {"a", "an", "the", "and", "to", "for", "of", "in"}}


def _value_dimensions(
    value: dict[str, Any], feedback: dict[str, Any], relationship: dict[str, Any] | None
) -> set[str]:
    if value.get("category") == "hard_rule" or value.get("active") is False:
        return set()
    if value.get("category") not in {"soft_value", "preference"}:
        return set()
    provenance = value.get("provenance", {})
    if provenance.get("source") not in {"stated", "inferred"}:
        return set()

    conditions = value.get("conditions", {})
    context = feedback.get("context") or {}
    context_text = " ".join(str(item) for item in context.values())
    context_tokens = _tokens(context_text)
    trigger = conditions.get("trigger")
    trigger_tokens = _tokens(trigger) if trigger else set()
    if trigger_tokens and not trigger_tokens <= context_tokens:
        return set()
    exceptions = value.get("exceptions", [])
    if any(
        exception_tokens and exception_tokens <= context_tokens
        for exception_tokens in (_tokens(exception) for exception in exceptions)
    ):
        return set()
    role = (
        relationship.get("identity", {}).get("role", "unknown")
        if relationship
        else "unknown"
    )
    applies_to_roles = conditions.get("applies_to_roles", [])
    if applies_to_roles and role != "unknown":
        compatible_roles = set(applies_to_roles)
        if role in {"parent", "sibling"}:
            compatible_roles.add("family")
        if role not in compatible_roles:
            return set()
    minimum_closeness = conditions.get("min_closeness")
    if minimum_closeness is not None:
        if not relationship:
            return set()
        closeness = relationship.get("scores", {}).get("closeness", {}).get("value")
        if closeness is None or float(closeness) < float(minimum_closeness):
            return set()

    user_id = feedback["user_id"]
    executed = feedback["executed"]
    preferred = value.get("behavioral_preference", {}).get("preferred_action", "")
    preference_text = " ".join(
        [
            str(preferred),
            str(value.get("statement", "")),
            str(value.get("value_name", "")),
        ]
    )
    preference_tokens = _tokens(preference_text)
    matched = set()
    for dimension in VALUE_DIMENSIONS:
        option = executed.get(dimension)
        if option is None:
            continue
        value_id = "VAL_" + _stable_id("", user_id, dimension)
        if value.get("_id") == value_id:
            matched.add(dimension)
            continue
        option_tokens = _tokens(option)
        if not option_tokens:
            continue
        if option_tokens <= preference_tokens or option_tokens & preference_tokens:
            matched.add(dimension)
    tone_guidance = value.get("behavioral_preference", {}).get("tone_guidance")
    if executed.get("tone") and _tokens(executed["tone"]) & _tokens(tone_guidance):
        matched.add("tone")
    return matched


def _matches_current_preference(
    value: dict[str, Any], dimensions: set[str], feedback: dict[str, Any]
) -> bool:
    for dimension in dimensions:
        value_id = "VAL_" + _stable_id("", feedback["user_id"], dimension)
        if value.get("_id") == value_id:
            return (
                value.get("behavioral_preference", {}).get("preferred_action")
                == str(feedback["executed"].get(dimension))
            )
    return True


def _value_statistics(value: dict[str, Any], memory: dict[str, Any]) -> tuple[float, float, int, int]:
    provenance = value.setdefault("provenance", {})
    supporting = list(dict.fromkeys(provenance.setdefault("supporting_episodes", [])))
    contradicting = list(dict.fromkeys(provenance.setdefault("contradicting_episodes", [])))
    provenance["supporting_episodes"] = supporting
    provenance["contradicting_episodes"] = contradicting
    episodes = {episode.get("_id"): episode for episode in memory["episodic_memory"]}
    supporting_scores = []
    for episode_id in supporting:
        episode = episodes.get(episode_id)
        if episode:
            score = _episode_signal(episode)["score"]
            supporting_scores.append((score if score is not None else 4.0) / 5.0)
    source = provenance.get("source", "inferred")
    pfb = (
        sum(supporting_scores) / len(supporting_scores)
        if supporting_scores
        else 0.8 if source == "stated" else 0.5
    )
    support_count, contradiction_count = len(supporting), len(contradicting)
    consistency = (
        support_count / (support_count + contradiction_count)
        if support_count + contradiction_count
        else 1.0
    )
    source_weight = 1.0 if source == "stated" else 0.6
    priority = _unit(max(0.1, 0.45 * pfb + 0.35 * consistency + 0.20 * source_weight))
    confidence = (
        1.0
        if source == "stated"
        else max(0.1, min(0.95, 0.50 + 0.08 * support_count - 0.12 * contradiction_count))
    )
    return priority, confidence, support_count, contradiction_count


def _refresh_value(value: dict[str, Any], memory: dict[str, Any], timestamp: str) -> None:
    priority, confidence, support_count, contradiction_count = _value_statistics(value, memory)
    value["priority_weight"] = priority
    provenance = value.setdefault("provenance", {})
    provenance["confidence"] = confidence
    provenance["last_validated_at"] = timestamp
    confirmed = provenance.get("source") == "stated" or confidence >= 0.85
    validation = value.setdefault("validation", {})
    validation.update(
        status=(
            "conflicting"
            if contradiction_count
            else "confirmed" if confirmed else "provisional"
        ),
        needs_user_confirmation=bool(contradiction_count) or not confirmed,
        contradiction_count=contradiction_count,
    )


def _new_value(
    user_id: str, dimension: str, preferred: Any, episode_id: str, episode_score: int, timestamp: str
) -> dict[str, Any]:
    label = dimension.replace("_", " ")
    value = {
        "_id": "VAL_" + _stable_id("", user_id, dimension),
        "user_id": user_id,
        "value_name": f"Action Block {label.title()} Preference",
        "category": "soft_value",
        "domain": "communication" if dimension in ("channel", "tone", "timing") else "actions",
        "statement": f"The user tends to prefer {preferred} for {label}.",
        "behavioral_preference": {
            "preferred_action": str(preferred),
            "avoid_actions": [],
            "tone_guidance": str(preferred) if dimension == "tone" else None,
        },
        "priority_weight": 0.1,
        "conditions": {},
        "exceptions": [],
        "provenance": {
            "source": "inferred",
            "confidence": 0.1,
            "created_at": timestamp,
            "last_validated_at": timestamp,
            "supporting_episodes": [episode_id],
            "contradicting_episodes": [],
        },
        "validation": {
            "status": "provisional",
            "needs_user_confirmation": True,
            "contradiction_count": 0,
        },
        "active": True,
    }
    _refresh_value(value, {"episodic_memory": [{
        "_id": episode_id,
        "decision_and_outcome": {"evaluation": {"user_feedback_score": episode_score}},
    }]}, timestamp)
    return value


def _merge_value(
    memory: dict[str, Any],
    feedback: dict[str, Any],
    episode_id: str,
    timestamp: str,
    relationship: dict[str, Any] | None,
) -> None:
    feedback_score = _feedback_score(feedback)
    valence = _emotional_valence(feedback_score)
    existing_dimensions: dict[str, bool] = {dimension: False for dimension in VALUE_DIMENSIONS}
    for value in memory["value_model"]:
        dimensions = _value_dimensions(value, feedback, relationship)
        if not dimensions:
            continue
        provenance = value.setdefault("provenance", {})
        supporting = provenance.setdefault("supporting_episodes", [])
        contradicting = provenance.setdefault("contradicting_episodes", [])
        if episode_id not in supporting and episode_id not in contradicting:
            matches_current_choice = _matches_current_preference(value, dimensions, feedback)
            if valence == "positive" and matches_current_choice:
                supporting.append(episode_id)
            elif valence == "negative" or (valence == "positive" and not matches_current_choice):
                contradicting.append(episode_id)
            else:
                continue
        for dimension in dimensions:
            existing_dimensions[dimension] = True
        _refresh_value(value, memory, timestamp)

    if valence != "positive":
        return
    for dimension in VALUE_DIMENSIONS:
        preferred = feedback["executed"].get(dimension)
        if preferred is None or existing_dimensions[dimension]:
            continue
        value_id = "VAL_" + _stable_id("", feedback["user_id"], dimension)
        existing = next((item for item in memory["value_model"] if item.get("_id") == value_id), None)
        if existing:
            if existing.get("category") == "hard_rule":
                continue
            if existing.get("category") not in {"soft_value", "preference"}:
                continue
            provenance = existing.setdefault("provenance", {})
            supporting = provenance.setdefault("supporting_episodes", [])
            contradicting = provenance.setdefault("contradicting_episodes", [])
            if episode_id not in supporting and episode_id not in contradicting:
                if existing.get("behavioral_preference", {}).get("preferred_action") == str(preferred):
                    supporting.append(episode_id)
                else:
                    contradicting.append(episode_id)
            _refresh_value(existing, memory, timestamp)
        else:
            memory["value_model"].append(
                _new_value(
                    feedback["user_id"], dimension, preferred, episode_id, feedback_score, timestamp
                )
            )


def merge_feedback(feedback: dict[str, Any], persona_memory: dict[str, Any]) -> dict[str, Any]:
    """Return a merged copy of a Persona Memory bundle and one feedback event.

    The bundle has three arrays named ``episodic_memory``, ``relationship_memory``,
    and ``value_model``, containing documents in the upstream repository's schemas.
    """
    _validate_feedback(feedback)
    if not isinstance(persona_memory, dict):
        raise ValueError("persona_memory must be an object")
    memory = copy.deepcopy(persona_memory)
    for collection in ("episodic_memory", "relationship_memory", "value_model"):
        if collection not in memory:
            memory[collection] = []
        if not isinstance(memory[collection], list):
            raise ValueError(f"persona_memory.{collection} must be an array")
        for document in memory[collection]:
            if not isinstance(document, dict):
                raise ValueError(f"persona_memory.{collection} entries must be objects")
            if document.get("user_id") != feedback["user_id"]:
                raise ValueError(f"persona_memory.{collection} contains a different user_id")

    episode_id = f"EP_{feedback['feedback_id']}"
    existing_episode = next(
        (item for item in memory["episodic_memory"] if item.get("_id") == episode_id),
        None,
    )
    if existing_episode:
        return memory

    timestamp = _timestamp(float(feedback["ts"]))
    episode = _episode(feedback, timestamp)
    memory["episodic_memory"].append(episode)
    relationship = _merge_relationship(memory, feedback, episode_id, timestamp)
    _merge_value(memory, feedback, episode_id, timestamp, relationship)
    return memory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feedback", required=True, type=Path, help="Action Block feedback JSON file")
    parser.add_argument("--memory", required=True, type=Path, help="Persona Memory bundle JSON file")
    parser.add_argument("--output", required=True, type=Path, help="Path for the merged memory JSON")
    args = parser.parse_args()

    feedback = json.loads(args.feedback.read_text(encoding="utf-8"))
    persona_memory = json.loads(args.memory.read_text(encoding="utf-8"))
    merged = merge_feedback(feedback, persona_memory)
    args.output.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
