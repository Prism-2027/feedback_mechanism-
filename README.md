# Feedback Mechanism

This repository contains persona-memory JSON schemas and a feedback merge implementation.

The implementation reads an Action Block feedback event and merges it into a Persona Memory bundle:

- `episodic_memory`: appends one cited episode per `feedback_id`
- `relationship_memory`: updates matching original relationship records in place
- `value_model`: updates matching soft values in place and creates inferred dimension preferences

Hard rules and stated relationship scores remain unchanged. Existing data is copied and updated in a new in-memory result; the source object is not modified. Reprocessing the same `feedback_id` is idempotent.

## Feedback format

`feedback_format.json` is an episodic feedback example using this repository's canonical field names. The merge API accepts an Action Block feedback object with:

- `feedback_id`, `user_id`, `snapshot_id`, `ts`
- `executed.action_type` and `executed.channel` (required)
- `response.outcome`: `accepted`, `modified`, `ignored`, `dismissed`, or `overridden`
- optional `response.user_feedback_score`: integer from 1 through 5
- optional `context`, `prediction`, `counterpart`, `rating`, `stakes`, `executed.tone`, and `executed.timing`

An explicit `response.user_feedback_score` takes precedence. If omitted, `rating` (`-1`, `0`, `1`) or the response outcome supplies a fallback 1–5 score.

## Run the merge locally

```bash
python3 feedback_mechanism.py \
  --feedback examples/feedback.json \
  --memory examples/persona_memory.json \
  --output merged_persona_memory.json
```

The memory bundle must contain arrays for `episodic_memory`, `relationship_memory`, and `value_model`. Records should follow the examples in `schemas/`.

## HTTP API

The HTTP API uses MongoDB as its persistence layer. It loads the user's three
memory collections, merges feedback, and upserts the resulting documents.
MongoDB's internal `_id` is user-scoped so records from different users cannot
overwrite one another; the persona document IDs are preserved when returned by
the API. If the user's database is empty, the optional `persona_memory` request
field can seed it once.

Start a local MongoDB server, then install dependencies and start the API:

```bash
docker run --name persona-memory-mongo -p 27017:27017 -d mongo:8
python3 -m pip install -r requirements.txt
export MONGODB_URI="mongodb://localhost:27017"
export MONGODB_DATABASE="persona_memory"
python3 -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Send `POST /feedback/merge` with the feedback. Optionally include a starting
memory bundle when the user's database has no records yet:

```json
{
  "feedback": {
    "feedback_id": "FB_EXAMPLE_001",
    "user_id": "USER_DEMO_014",
    "snapshot_id": "SIT_014",
    "ts": 1795000000,
    "executed": {
      "action_type": "show_meeting_brief",
      "channel": "calendar"
    },
    "response": {
      "outcome": "accepted",
      "user_feedback_score": 5
    }
  },
  "persona_memory": {
    "episodic_memory": [],
    "relationship_memory": [],
    "value_model": []
  }
}
```

`GET /health` checks the MongoDB connection. The FastAPI `/docs` interface
exposes the complete feedback contract. The local JSON CLI remains available
for one-off file-based merges and does not write to MongoDB.

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests cover idempotency, schema preservation, hard-rule preservation,
relationship/value updates, conflicting evidence, feedback-score validation,
and the MongoDB-backed HTTP endpoint.
