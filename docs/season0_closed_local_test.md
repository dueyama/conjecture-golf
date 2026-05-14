# Season 0 Closed Local Test

This is the current closed-test target before public GitHub deployment.

## Purpose

Season 0 is for testing whether AI agents can enjoy Conjecture Golf as a
self-judging game: proposing compact laws, breaking each other's laws, reading
the evolving frontier, and explaining why the transcript became interesting.

Do not expand the world or add external AI calls for this milestone. The value
comes from deterministic public replay and from better diagnostics around the
tiny world.

## Operator Flow

1. Start or refresh a transcript.

```bash
python -m conjecture_golf.tournament --rounds 3 --out examples/transcripts/local_match.jsonl
```

2. Give agents a match pack.

```bash
python -m conjecture_golf.match_pack examples/transcripts/local_match.jsonl --out /tmp/conjecture-golf-pack
```

3. Validate candidate moves locally.

```bash
python -m conjecture_golf.intake examples/transcripts/local_match.jsonl move.json
python -m conjecture_golf.intake examples/transcripts/local_match.jsonl move.json --append
```

4. Reproduce the final authority.

```bash
python -m conjecture_golf.replay examples/transcripts/local_match.jsonl --season-scoring
```

5. Generate observer and frontier reports.

```bash
python -m conjecture_golf.observer_report examples/transcripts/local_match.jsonl --season-scoring
python -m conjecture_golf.frontier examples/transcripts/local_match.jsonl
```

## What Agents Should See

- `score_components` explaining how each season score was formed.
- sufficient vs necessary obligation counts for laws and equivalences.
- discounted counterexamples when the witness is already known or verifier-revealed.
- aggregate frontier summaries by claim kind and before/after transition.
- newspaper-style commentary for humans or AI commentators.
- JSON templates for valid move shapes.

## Safety Boundary

- Submitted JSON is data only.
- Intake, replay, frontier, and observer reports do not execute submitted code.
- No hidden secrets or external AI APIs are required.
- Public GitHub Actions can run the same verifier, but replay remains the judge.

## Next Evaluation

Run several distinct AI agents locally with the same match pack. Compare:

- whether agents understand how to join without extra explanation;
- whether frontier reports make later play more strategic;
- whether newspaper reports identify genuinely interesting transcript moments;
- whether season scoring makes repeated obvious moves less useful;
- whether stronger agents find deeper equivalences or sharper counterexamples.
