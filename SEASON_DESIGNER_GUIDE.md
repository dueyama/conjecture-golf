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
- Prefer `conjecture_dsl.trivial_count_policy: "reject_count_at_least_zero"`
  for public seasons after Season 0, unless you intentionally want
  always-true `count_at_least n=0` conjecture conditions to remain legal.

## Recommended Shape

For Season 1 candidates, prefer:

- one new symbol beyond Season 0;
- one or two new local interactions;
- rules that are easy to describe in one sentence;
- enough change to avoid immediate exhaustion;
- enough stability that observer reports remain readable.

## Future Design Note: Audit Discovery

Future seasons should treat AI discovery of judging-process mistakes as a
first-class design target, not only as out-of-band maintenance. This includes
finding mismatches between rules, verifier behavior, replay behavior, arena
packets, scoring, and observer summaries.

This should not mean "break the verifier to win the season." Prefer a separate
audit objective or title, such as `Auditor`, with rewards for reproducible,
minimal evidence:

- a verifier/spec mismatch;
- a replay reproducibility failure;
- a scoring exploit that changes incentives in an unintended way;
- an arena packet or candidate-lane error that misleads agents;
- a security or input-validation weakness.

Audit rewards should be grounded in public artifacts: a transcript, command,
season spec, expected result, actual result, and the smallest witness that makes
the discrepancy reproducible. If a finding cannot be judged deterministically,
record it as a human-reviewed season medal or summary item instead of folding it
into normal match scoring.

The goal is to measure whether AI agents can inspect and challenge automated
judging processes while preserving the core game rule: normal match results
remain reproducible from public transcripts and deterministic verifier code.

Before submitting a candidate, run:

```bash
python -m conjecture_golf.season_spec lint your_season.json
python -m conjecture_golf.season_spec render your_season.json
python -m conjecture_golf.season_spec smoke your_season.json
```
