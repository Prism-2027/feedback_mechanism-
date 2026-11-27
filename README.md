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
  --feedback feedback.json \
  --memory persona_memory.json \
  --output merged_persona_memory.json
```

The memory bundle must contain arrays for `episodic_memory`, `relationship_memory`, and `value_model`. Records should follow the examples in `schemas/`.

## HTTP API

Install dependencies and start the API:

```bash
python3 -m pip install -r requirements.txt
python3 -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Send `POST /feedback/merge` with:

```json
{
  "feedback": {},
  "persona_memory": {
    "episodic_memory": [],
    "relationship_memory": [],
    "value_model": []
  }
}
```

The FastAPI `/docs` interface exposes the complete contract. `/health` reports API readiness.

## Tests

```bash
python3 -m unittest discover -s tests
```

The tests cover idempotency, schema preservation, hard-rule preservation, relationship/value updates, conflicting evidence, feedback-score validation, and the HTTP endpoint.
