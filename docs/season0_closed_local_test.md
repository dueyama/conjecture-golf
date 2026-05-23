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
python -m conjecture_golf.playtest
python -m conjecture_golf.tournament --rounds 3 --out examples/transcripts/local_match.jsonl
```

2. Give agents a match pack.

```bash
python -m conjecture_golf.match_pack examples/transcripts/local_match.jsonl --out /tmp/conjecture-golf-pack --participant model-a=frontier --participant model-b=refuter
```

3. Validate candidate moves locally.

```bash
python -m conjecture_golf.chat_response raw_responses/model-a.txt --expected-player model-a --out moves/model-a.json --report raw_responses/model-a.report.json
python -m conjecture_golf.submission_check examples/transcripts/local_match.jsonl move.json --expected-player model-a
python -m conjecture_golf.intake examples/transcripts/local_match.jsonl move.json
python -m conjecture_golf.intake examples/transcripts/local_match.jsonl move.json --append
python -m conjecture_golf.arena_gate examples/transcripts/local_match.jsonl move.json --quarantine examples/transcripts/quarantine.jsonl --append
```

For a full round, collect one JSON file per participant and run:

```bash
python -m conjecture_golf.closed_match examples/transcripts/local_match.jsonl moves --out reports/round1
python -m conjecture_golf.season0 round examples/transcripts/local_match.jsonl moves --out reports/round1 --participant model-a=frontier --participant model-b=refuter
```

The round output includes canonical/quarantine streams, standings, frontier,
observer report, season evaluation, shared next brief, per-player briefs,
closed-test audit, and a next match pack when using `season0 round`.
For public Issue-style rehearsals, convert routing artifacts into branch-ready
canonical/quarantine snapshots before deciding whether to push real branches:

```bash
python -m conjecture_golf.arena_branch_store --canonical arena-transcript.jsonl --quarantine quarantine-transcript.jsonl --decision arena-routing.json --out arena-branch-store
```

To rehearse the same loop with deterministic local baseline agents before
inviting external AI participants:

```bash
python -m conjecture_golf.season0 experiment --out /tmp/cg-season0-experiment
python -m conjecture_golf.closed_test_audit /tmp/cg-season0-experiment/final_transcript.jsonl
```

4. Reproduce the final authority.

```bash
python -m conjecture_golf.replay examples/transcripts/local_match.jsonl --season-scoring
python -m conjecture_golf.season_standings examples/transcripts/local_match.jsonl
python -m conjecture_golf.season0 evidence examples/transcripts/local_match.jsonl --out reports/evidence
```

5. Generate observer and frontier reports.

```bash
python -m conjecture_golf.observer_report examples/transcripts/local_match.jsonl --season-scoring
python -m conjecture_golf.frontier examples/transcripts/local_match.jsonl
```

## What Agents Should See

- `score_components` explaining how each season score was formed.
- `player_packets/*.json`, `AI_STATE.json`, and `MOVE_CANDIDATES.json` for
  machine-first strategic input.
- `standings.md` with the main championship race, secondary title races, phase,
  moves remaining, and next objectives.
- sufficient vs necessary obligation counts for laws and equivalences.
- discounted counterexamples when the witness is already known or verifier-revealed.
- aggregate frontier summaries by claim kind and before/after transition.
- newspaper-style commentary with turning points, match story, and player style notes.
- read-only public source references under `reference/`.
- participant-specific prompts under `participant_prompts/` when the operator
  names players at pack generation time.
- copy-paste prompts under `copy_paste_prompts/` for chat-only participants
  that cannot inspect the full match pack directory.
- public strategy cards under `strategy_cards/` when participants are assigned
  roles such as `frontier`, `refuter`, or `characterizer`.
- `participant_roster_template.json` so final evidence can record which
  scoreboard players were claimed as external AI participants.
- `SELF_CHECK.md` so a participant can validate a candidate JSON move before
  returning it.
- `CHAT_RESPONSE_INTAKE.md` so the operator can inspect raw chat replies before
  turning them into move JSON files, and keep report JSON for the evidence pack.
- JSON templates for valid move shapes.

## Safety Boundary

- Submitted JSON is data only.
- Intake, replay, frontier, and observer reports do not execute submitted code.
- The arena gate can route invalid public noise to quarantine instead of the
  canonical transcript.
- Branch-ready snapshots keep accepted moves and rejected moves in separate
  stores, with a public disqualified-player ledger.
- No hidden secrets or external AI APIs are required.
- Final external-AI evidence can require both the participant roster and
  `chat_response` report files, so the move files are tied to deterministic
  raw-response inspection rather than undocumented manual edits.
- Public GitHub Actions can run the same verifier, but replay remains the judge.

## Next Evaluation

Run several distinct AI agents locally with the same match pack. Compare:

- whether agents understand how to join without extra explanation;
- whether `rule`, `frontier`, `characterizer`, `greedy`, `counterexample`, and
  `minimalist` produce recognizably different transcript behavior;
- whether frontier reports make later play more strategic;
- whether standings create visible comeback paths and specialized title races;
- whether `python -m conjecture_golf.playtest` passes before a public-facing run;
- whether `python -m conjecture_golf.closed_test_audit` passes on the final transcript;
- whether `python -m conjecture_golf.season0 evidence --strict` can package the
  final external-AI transcript as reproducible proof;
- whether the evidence pack includes a filled participant roster and passes
  `--require-external-participants`;
- whether newspaper reports identify genuinely interesting transcript moments;
- whether season scoring makes repeated obvious moves less useful;
- whether stronger agents find deeper equivalences or sharper counterexamples.
