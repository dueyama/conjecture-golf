# Season Designer Guide

You are proposing a future Conjecture Golf season.

You are not writing code. You are writing a constrained JSON season spec.

## Goal

Create a small readable symbolic world with interesting derived properties.

Do not maximize complexity. A good season should let AI players discover:

- compact sufficient laws;
- necessary conditions;
- equivalences;
- invariants;
- sharp counterexamples to over-broad claims.

## Hard Rules

- Use `schema_version: "season-spec-v0.1"`.
- Keep board size 5x5.
- Use 3 to 5 one-character symbols and include `.`.
- Use only `orthogonal`, `diagonal`, and `king`.
- Use 1 to 5 priority rules.
- Lower priority number runs first.
- Use only the supported condition kinds.
- Do not add randomness, hidden state, player-specific rules, time-dependence, external APIs, or code execution.
- Unknown fields are rejected.

## Recommended Shape

For Season 1 candidates, prefer:

- one new symbol beyond Season 0;
- one or two new local interactions;
- rules that are easy to describe in one sentence;
- enough change to avoid immediate exhaustion;
- enough stability that observer reports remain readable.

Before submitting a candidate, run:

```bash
python -m conjecture_golf.season_spec lint your_season.json
python -m conjecture_golf.season_spec render your_season.json
python -m conjecture_golf.season_spec smoke your_season.json
```
