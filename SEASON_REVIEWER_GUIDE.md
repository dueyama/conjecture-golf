# Season Reviewer Guide

Review proposed Conjecture Golf seasons as data-only specs.

Do not execute submitted code. A season proposal must be JSON that passes the
fixed linter and engine.

## Review Roles

- `safety-reviewer`: rejects execution, determinism, replay, or abuse risks.
- `playability-reviewer`: checks whether the world is trivial, chaotic, exhausted too quickly, or unreadable.
- `observer-critic`: checks whether a human can follow the match story.
- `operator-reviewer`: recommends accept, revise, or reject.

## Suggested Review JSON

```json
{
  "type": "season_review",
  "reviewer": "playability-reviewer",
  "season_id": "season_1_moss_candidate",
  "recommendation": "revise",
  "scores": {
    "safety": 10,
    "determinism": 10,
    "readability": 7,
    "playability": 6,
    "novelty": 5
  },
  "major_concerns": [
    "Moss appears but never disappears, so invariants may dominate."
  ],
  "suggested_changes": [
    "Add one simple disappearance rule for isolated moss."
  ]
}
```

## Minimum Checks

```bash
python -m conjecture_golf.season_spec lint candidate.json
python -m conjecture_golf.season_spec metrics candidate.json --json
python -m conjecture_golf.season_spec render candidate.json
python -m conjecture_golf.season_spec smoke candidate.json
```

Reject specs that require arbitrary code, randomness, hidden state, new board
sizes, unsupported relations, or unknown fields.
