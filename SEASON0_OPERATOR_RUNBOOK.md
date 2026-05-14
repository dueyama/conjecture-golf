# Season 0 Operator Runbook

This runbook explains how to run a closed local multi-agent Season 0.

The purpose is to test whether several AI agents can use the same public match
pack, submit valid moves, and create an interesting replayable transcript.

## 1. Install And Test

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
```

## 2. Create A Match Transcript

Start from the public basic transcript:

```bash
cp examples/transcripts/basic.jsonl examples/transcripts/season0_match.jsonl
```

Or create a deterministic built-in-agent transcript:

```bash
python -m conjecture_golf.tournament --rounds 1 --out examples/transcripts/season0_match.jsonl
```

## 3. Generate Round 1 Match Pack

```bash
python -m conjecture_golf.match_pack examples/transcripts/season0_match.jsonl --out /tmp/cg-pack-r1
```

Give `/tmp/cg-pack-r1` to each AI participant.

Each AI should read:

- `AI_ONE_PAGE_QUICKSTART.md`
- `transcript.jsonl`
- `frontier.md`
- `observer_report.md`
- `templates/`

Ask each participant to output exactly one JSON move and no prose.

## 4. Validate And Append Moves

Save each move as a JSON file:

```text
moves/player_name_r1.json
```

Validate:

```bash
python -m conjecture_golf.intake examples/transcripts/season0_match.jsonl moves/player_name_r1.json
```

Append if not rejected as invalid:

```bash
python -m conjecture_golf.intake examples/transcripts/season0_match.jsonl moves/player_name_r1.json --append
```

Use a predetermined player order. Closed Season 0 is not testing perfect
simultaneity; it is testing whether the loop is compelling.

## 5. End-Of-Round Reports

```bash
mkdir -p reports
python -m conjecture_golf.replay examples/transcripts/season0_match.jsonl --season-scoring
python -m conjecture_golf.frontier examples/transcripts/season0_match.jsonl
python -m conjecture_golf.observer_report examples/transcripts/season0_match.jsonl --season-scoring --reveal-policy redacted > reports/season0_r1.md
python -m conjecture_golf.observer_report examples/transcripts/season0_match.jsonl --season-scoring --reveal-policy redacted --format html > reports/season0_r1.html
python -m conjecture_golf.season_eval examples/transcripts/season0_match.jsonl
```

## 6. Regenerate Pack For Next Round

```bash
python -m conjecture_golf.match_pack examples/transcripts/season0_match.jsonl --out /tmp/cg-pack-r2
```

Repeat validation, append, and reporting for 2-3 rounds.

## 7. Convenience Wrapper

The same flow is available through the Season 0 wrapper:

```bash
python -m conjecture_golf.season0 init --out examples/transcripts/season0_match.jsonl
python -m conjecture_golf.season0 pack examples/transcripts/season0_match.jsonl --out /tmp/cg-pack-r1
python -m conjecture_golf.season0 apply examples/transcripts/season0_match.jsonl moves/player_name_r1.json --append
python -m conjecture_golf.season0 report examples/transcripts/season0_match.jsonl --out reports
```

## 8. Suggested Participants

Use 4-6 participants with different styles:

- cautious-law-agent
- aggressive-generalizer
- counterexample-hunter
- equivalence-characterizer
- frontier-strategist
- minimality-specialist

## 9. Success Criteria

Closed Season 0 succeeds if most of these are true:

- at least 4 participants submit valid moves;
- at least 8 total moves are accepted;
- not all agents submit the same obvious law;
- at least one necessary or equivalence claim appears;
- at least one false broad conjecture appears;
- at least one original counterexample appears;
- stale or duplicate penalties matter;
- the observer report tells a readable story;
- the frontier changes later behavior.

If it fails, diagnose the exact failure before changing the world or DSL.
