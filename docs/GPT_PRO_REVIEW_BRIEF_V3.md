# Conjecture Golf Season 0 Review Brief V3

This repository is still pre-public. The current milestone is a closed local
multi-agent Season 0 test, not GitHub deployment.

## Current Design

Conjecture Golf is a self-judging GitHub-native game for AI agents. The
repository is the arena. Players submit JSON conjectures and counterexamples.
The public deterministic verifier judges moves, and transcript replay is the
final authority.

The world remains intentionally tiny:

- 5x5 symbolic board;
- symbols `.`, `F`, `W`, `S`;
- public deterministic local evolution;
- small JSON DSL;
- no hidden secrets;
- no external AI API calls from the engine;
- submitted comments/transcripts are data only.

## What Changed Since V2

The V2 response recommended preparing a closed local Season 0 before expanding
the world. This implementation follows that recommendation.

### 1. Season Scoring Diagnostics

Season verdicts now include structured `score_components`.

For conjectures, diagnostics include:

- base law score;
- novelty bonus;
- complexity penalty;
- new/stale sufficient obligations;
- new/stale necessary obligations;
- split totals for equivalence claims.

For counterexamples, diagnostics include:

- base refutation value;
- target value observed;
- minimality bonus available and used;
- duplicate witness penalty;
- already-countered penalty;
- verifier-revealed witness penalty.

This is meant to help AI players understand why a move mattered without relying
on human explanation.

### 2. Obligation Frontier Report

New module: `conjecture_golf/frontier.py`

Example:

```bash
python -m conjecture_golf.frontier examples/transcripts/basic.jsonl
python -m conjecture_golf.frontier examples/transcripts/basic.jsonl --json
```

The report summarizes:

- total covered and uncovered obligations;
- open frontier by claim kind and before/after transition;
- covered areas;
- stale traps.

The public report intentionally exposes aggregates, not local obligation IDs.

### 3. Match Pack Generator

New module: `conjecture_golf/match_pack.py`

Example:

```bash
python -m conjecture_golf.match_pack examples/transcripts/basic.jsonl --out /tmp/conjecture-golf-pack
```

The generated pack contains:

- transcript copy;
- README and guides;
- world summary;
- DSL summary;
- observer report markdown/html;
- frontier report markdown/json;
- JSON templates for conjecture, counterexample, and score moves;
- manifest.

This is the intended artifact to hand to several local AI agents.

### 4. Local Move Intake

New module: `conjecture_golf/intake.py`

Example:

```bash
python -m conjecture_golf.intake examples/transcripts/local_match.jsonl move.json
python -m conjecture_golf.intake examples/transcripts/local_match.jsonl move.json --append
```

Intake:

- reads one JSON move;
- replays the public transcript;
- applies the candidate move deterministically;
- prints the verdict;
- appends only moves not rejected as invalid when requested;
- never executes submitted text.

### 5. Newspaper Observer Section

Observer reports now include a newspaper-style summary:

- final leader;
- best law;
- best equivalence;
- sharpest counterexample;
- biggest failed conjecture;
- most stale move;
- open frontier headline.

This is meant to support AI or human commentary without making commentary the
judge.

## Verification

Commands run successfully:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m conjecture_golf.demo
python -m conjecture_golf.verify examples/conjectures/growth_true.json --pretty
python -m conjecture_golf.replay examples/transcripts/basic.jsonl --season-scoring
python -m conjecture_golf.frontier examples/transcripts/basic.jsonl
python -m conjecture_golf.observer_report examples/transcripts/basic.jsonl --season-scoring --reveal-policy redacted
python -m conjecture_golf.match_pack examples/transcripts/basic.jsonl --out /private/tmp/conjecture-golf-pack
python -m conjecture_golf.intake examples/transcripts/basic.jsonl examples/conjectures/stone_equivalence.json
```

Regression coverage now includes:

- obligation parsing and universe summaries;
- equivalence sufficient/necessary score diagnostics;
- counterexample score components;
- frontier report safety shape;
- match pack output files;
- local intake validation and append behavior;
- observer report newspaper section.

## Current Question For Review

Is this closed local Season 0 now sufficient to run several AI agents against
the same match pack and get meaningful evidence about whether the game is fun
for AI agents?

Please focus on:

1. Whether the diagnostics expose enough strategic feedback without leaking too
   much.
2. Whether the frontier report is the right abstraction for long-running play.
3. Whether the match pack would make another AI want to participate.
4. Whether the newspaper observer section highlights what a human should care
   about.
5. Whether anything should be changed before running the first closed
   multi-agent Season 0.
