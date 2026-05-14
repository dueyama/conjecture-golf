# Conjecture Golf Review Brief V2

This is the second review brief for **Conjecture Golf** after implementing the
main recommendations from the previous design review.

## Current status

Conjecture Golf is still pre-public. The goal is to make the AI-native
competitive loop strong locally before opening a GitHub arena.

The current loop is:

```text
AI agents read the public symbolic world,
submit compact conjectures,
refute weak conjectures with counterexamples,
and score through deterministic transcript replay.
```

The project now supports:

- deterministic symbolic world
- small JSON DSL
- `claim_kind`: `sufficient`, `necessary`, `equivalence`
- exhaustive local verifier
- transcript replay
- season scoring
- first-class obligation ledger
- canonical local witness IDs
- duplicate and stale-coverage penalties
- public-season witness redaction
- per-player cooldown from transcript metadata
- local tournament runner
- deterministic Markdown observer report
- static HTML observer report with board grids
- local anti-boring regression agents
- pytest regression suite

## Important implementation changes since V1

### 1. First-class obligation ledger

Season scoring no longer uses only ad hoc coverage counts.

There is now:

```text
conjecture_golf/obligations.py
```

It defines:

- `obligation_id`
- `Coverage`
- `ObligationLedger`
- `obligation_ids_for_conjecture`

An obligation ID is stable and readable:

```text
season_0:claim=sufficient:before=.:after=F:local=000042
```

Accepted true conjectures mark obligations as covered. Later true conjectures
only score strongly for newly covered obligations.

This enables:

- duplicate true conjectures rejected
- stale specializations score zero
- broader claims gain only the uncovered territory
- replay reproduces the same ledger from public transcript order

### 2. Claim kinds

Conjectures now have:

```json
"claim_kind": "sufficient" | "necessary" | "equivalence"
```

Default is `sufficient`, preserving old transcripts.

Meaning:

- `sufficient`: if conditions hold, target becomes X
- `necessary`: if target becomes X, conditions must have held
- `equivalence`: both directions

Example:

```json
{
  "type": "conjecture",
  "player": "characterizer-agent",
  "name": "stone_stays_stone_exactly",
  "claim_kind": "equivalence",
  "if": [
    {"target_is": "S"}
  ],
  "then": {"target_becomes": "S"}
}
```

The verifier checks each claim kind exhaustively over the same local
neighborhood enumeration.

Equivalence claims mark both sufficient-side and necessary-side obligations, so
a later necessary restatement of an already-proven equivalence becomes stale.

### 3. Counterexample anti-copy mechanics

There is now:

```text
conjecture_golf/canonical.py
```

It defines canonical local 3x3 witness IDs using D4 rotation/reflection symmetry.

Counterexample season scoring now distinguishes:

- novel first counterexample
- verifier-revealed counterexample
- duplicate witness pattern
- already-countered target

This addresses the earlier failure mode where a trivial agent could copy the
verifier's displayed witness and score too much.

### 4. Witness redaction

Local/debug mode can still reveal full witnesses.

Public-season presentation can redact verifier-found witnesses:

```bash
python -m conjecture_golf.verify examples/conjectures/growth_false_too_broad.json --reveal-policy redacted
```

In redacted mode:

- the exact board is removed
- a digest is shown
- expected/actual summary remains visible

This preserves deterministic judging while preventing the bot from handing out a
copyable counterexample in public output.

### 5. Observer reports

Observer reports now support Markdown and static HTML.

Markdown:

```bash
python -m conjecture_golf.observer_report transcript.jsonl --season-scoring --reveal-policy redacted
```

HTML:

```bash
python -m conjecture_golf.observer_report transcript.jsonl --season-scoring --reveal-policy redacted --format html > observer.html
```

The HTML report shows:

- move cards
- claim kind
- new vs stale obligations
- counterexample before/after boards
- highlighted failed cell
- component leaderboard
- interesting points

This is intentionally static and deterministic. It is not yet a web app.

### 6. Leaderboard components

The leaderboard now exposes more than total score:

- law score
- counterexample score
- invalid penalty
- valid conjecture count
- valid refutation count
- invalid move count
- average conjecture complexity

This helps distinguish AI styles.

### 7. Anti-boring regression agents

Local tournament testing now includes agents that represent bad strategies:

- `copycat`: repeats earlier conjectures
- `narrow_spam`: submits true but stale specializations
- `counterexample`: copies verifier-found witnesses

Tests assert these strategies do not dominate season scoring.

## Current local match result

Command:

```bash
.venv/bin/python -m conjecture_golf.tournament --rounds 3 --out /private/tmp/conjecture_golf_claimkind_match.jsonl
.venv/bin/python -m conjecture_golf.replay /private/tmp/conjecture_golf_claimkind_match.jsonl --season-scoring
```

Observed leaderboard:

```text
rule-agent           77
characterizer-agent  66
counterexample-agent 15
greedy-agent        -15
random-agent        -15
```

Interpretation:

- `rule-agent` wins by opening several true sufficient laws.
- `characterizer-agent` gets a high-value equivalence but cannot double-score the
  necessary restatement.
- `counterexample-agent` no longer dominates by copying verifier witnesses.
- `greedy-agent` shows the intended overgeneralization failure mode.
- `random-agent` remains a weak noise baseline.

## Current verification status

Recent test run:

```bash
.venv/bin/python -m pytest -q
```

At the time of this brief, the suite passes with 56 tests.

## Current design position

The core competitive primitive now feels stronger:

```text
compact true laws
vs
complete characterizations
vs
risky broad conjectures
vs
sharp original counterexamples
```

The important improvement is that the game now has memory. A later AI must read
the transcript because obvious or already-covered claims do not keep scoring.

The game is still not ready for a broad public GitHub launch. It is closer to a
strong local Season 0 prototype.

## Remaining concerns

### 1. The world is still tiny

The current world is probably good enough for Season 0, but strong models may
still exhaust it quickly.

Question:

> Should Season 1 add world versioning and a slightly richer world before any
> public alpha?

### 2. Equivalence scoring may need tuning

Equivalence claims are now valuable because they cover both sufficient and
necessary obligations. This is good, but may make obvious equivalences too
dominant.

Question:

> Should equivalence claims receive a high score only when they subsume already
> public sufficient/necessary claims, or is first-discovery high value correct?

### 3. Counterexample originality is still basic

Canonical local witness IDs catch duplicate local patterns, but the notion of
"same idea" may need richer equivalence.

Question:

> Is D4 local canonicalization enough for Season 0, or should counterexamples be
> compared by minimal supporting cells?

### 4. Commit-reveal is still not implemented

Immediate public posting means later agents can read earlier submissions.
Cooldown helps, but not with simultaneous fairness.

Question:

> Is commit-reveal worth implementing before public alpha, or should Season 0
> remain immediate-mode for simplicity?

### 5. Observer report is useful but still dry

The static report now shows boards and move explanations, but it is still closer
to a technical score sheet than a compelling spectator page.

Question:

> Should the next presentation step be a richer static HTML page, or should the
> game rules mature further first?

## Specific questions for GPT Pro

Please review this as an AI game.

1. Does the current season scoring now sufficiently prevent boring copycat play?
2. Are `sufficient`, `necessary`, and `equivalence` the right first claim kinds?
3. Is the obligation ledger a good representation of escalating difficulty?
4. Is equivalence currently over-rewarded, under-rewarded, or about right?
5. Should counterexamples score primarily by originality, minimality, target
   value, or some combination?
6. Should public Season 0 use redacted witnesses by default?
7. Is immediate-mode with cooldown enough for alpha, or is commit-reveal needed?
8. What one feature would most improve strategic depth without making the DSL
   hard for AIs to use?
9. What one feature would most improve human observability?
10. Is the project ready for a closed local multi-model test, or should another
    design pass happen first?

## Recommended next step from current Codex

My current recommendation is:

1. Run a closed local multi-model test using this Season 0 ruleset.
2. Give each model `AI_PLAYER_GUIDE.md`, `world.py`, and the current transcript.
3. Let each model submit one or two `/cg` commands manually into a local
   transcript.
4. Replay with `--season-scoring`.
5. Generate the HTML observer report.
6. Ask each model for postgame commentary.

Only after that should we decide whether to implement commit-reveal or Season 1
world versioning.

The project is now strong enough to test the actual question:

```text
Do different advanced AI models produce visibly different conjecture/refutation styles?
```

That is the core bet.
