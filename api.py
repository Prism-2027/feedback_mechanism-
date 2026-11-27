"""FastAPI endpoint for merging Action Block feedback into Persona Memory."""

from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from feedback_mechanism import merge_feedback


class ExecutedAction(BaseModel):
    action_type: str
    channel: str
    tone: str | None = None
    timing: str | None = None


class UserResponse(BaseModel):
    outcome: Literal["accepted", "modified", "ignored", "dismissed", "overridden"]
    latency_ms: int | None = None
    user_action: str | None = None
    user_feedback_score: int | None = Field(default=None, ge=1, le=5)


class ActionPrediction(BaseModel):
    top: str
    confidence: float = Field(ge=0, le=1)
    probs: dict[str, float] = Field(default_factory=dict)


class Feedback(BaseModel):
    feedback_id: str
    user_id: str
    snapshot_id: str
    ts: float
    context: dict[str, str] = Field(default_factory=dict)
    executed: ExecutedAction
    response: UserResponse
    prediction: ActionPrediction | None = None
    counterpart: str | None = None
    rating: Literal[-1, 0, 1] | None = None
    stakes: Literal["low", "medium", "high"] = "low"


class MergeRequest(BaseModel):
    feedback: Feedback
    persona_memory: dict[str, Any]


app = FastAPI(title="Persona Memory Feedback Merger", version="1.0.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/feedback/merge")
def merge(request: MergeRequest) -> dict[str, Any]:
    try:
        return merge_feedback(
            request.feedback.model_dump(exclude_none=True),
            request.persona_memory,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
