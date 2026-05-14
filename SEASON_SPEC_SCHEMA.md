# Season Spec v0.1 Schema

Season specs are data-only JSON files. They define symbolic worlds for
Conjecture Golf without allowing submitted Python code.

## Required Top-Level Fields

```text
schema_version
season_id
title
summary
designer
board
symbols
relations
transition
conjecture_dsl
presentation
limits
```

Unknown fields are rejected.

## Fixed v0.1 Limits

- `schema_version` must be `season-spec-v0.1`.
- board `width` and `height` must both be `5`.
- symbols: 3 to 5 one-character printable ids, including `.`.
- relations: only `orthogonal`, `diagonal`, `king`.
- `transition.default` must be `stay`.
- rules: 1 to 5 priority rules.
- lower numeric `priority` runs first.
- the first matching rule decides the next symbol.
- no randomness, hidden state, player-specific behavior, time-dependence, code callbacks, or nested boolean logic.

## Conditions

Supported condition kinds match the Season 0 conjecture DSL:

```json
{"target_is": "."}
{"exists": {"symbol": "W", "relation": "diagonal"}}
{"not_exists": {"symbol": "S", "relation": "king"}}
{"count_at_least": {"symbol": "S", "relation": "orthogonal", "n": 2}}
{"count_exactly": {"symbol": "W", "relation": "orthogonal", "n": 2}}
```

## Commands

```bash
python -m conjecture_golf.season_spec lint seasons/season_0.json
python -m conjecture_golf.season_spec metrics seasons/season_0.json --json
python -m conjecture_golf.season_spec render seasons/season_0.json
python -m conjecture_golf.season_spec smoke seasons/season_0.json
```
