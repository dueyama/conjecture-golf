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
- no randomness, hidden state, player-specific behavior, time-dependence, code callbacks, or unbounded boolean logic.

## Conditions

Supported condition kinds match the Season 0 conjecture DSL:

```json
{"target_is": "."}
{"exists": {"symbol": "W", "relation": "diagonal"}}
{"not_exists": {"symbol": "S", "relation": "king"}}
{"count_at_least": {"symbol": "S", "relation": "orthogonal", "n": 2}}
{"count_exactly": {"symbol": "W", "relation": "orthogonal", "n": 2}}
```

Season 2 may enable bounded disjunction for conjectures:

```json
{
  "any_of": [
    [{"target_is": "M"}],
    [
      {"target_is": "."},
      {"count_at_least": {"symbol": "S", "relation": "orthogonal", "n": 2}}
    ]
  ]
}
```

When enabled, `any_of` is capped by
`conjecture_dsl.max_any_of_branches` and
`conjecture_dsl.max_any_of_branch_conditions`; nested `any_of` is invalid.

## Conjecture DSL Options

`conjecture_dsl.trivial_count_policy` is optional.

- `allow`: keep the Season 0 behavior.
- `reject_count_at_least_zero`: reject submitted conjectures that use
  `count_at_least` with `n: 0`. This does not reject `count_exactly` with
  `n: 0`, because absence can be informative.

## Competition Options

`competition` is optional. If omitted, the champion is the raw total-score
leader. Season 2 uses:

```json
{
  "competition": {
    "victory": "title_points",
    "title_points": {"first": 5, "second": 3, "third": 1}
  }
}
```

With `title_points`, standings still show raw score, but the champion is the
player with the best combined title-race performance.

## Commands

```bash
python -m conjecture_golf.season_spec lint seasons/season_0.json
python -m conjecture_golf.season_spec metrics seasons/season_0.json --json
python -m conjecture_golf.season_spec render seasons/season_0.json
python -m conjecture_golf.season_spec smoke seasons/season_0.json
```
