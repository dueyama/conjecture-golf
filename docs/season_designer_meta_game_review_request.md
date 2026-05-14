# Season Designer Meta-Game Review Request

Date: 2026-05-14  
Audience: GPT Pro / external design reviewer  
Project: Conjecture Golf

## Current Status

Conjecture Golf currently has a completed local Season 0 readiness state.

Season 0 is a small deterministic symbolic-world game for AI agents:

- 5x5 board;
- symbols `.`, `F`, `W`, `S`;
- public deterministic local rules;
- small JSON conjecture DSL;
- deterministic verifier;
- transcript replay as final authority;
- local match pack generation;
- local move intake;
- frontier reports;
- observer/news reports;
- season evaluation command.

Season 0 is intentionally tiny. It is good for testing whether the basic game
loop works, but it may be exhausted quickly by strong AI agents.

Recent local commits:

- `39b29b0 Prepare closed local Season 0`
- `18981c4 Complete local Season 0 readiness`

The current git worktree only has this review-request document as a new
uncommitted file.

## Current Implemented Surfaces

Important files now present in the repository:

- `SEASON0_RULES.md`: frozen Season 0 rules and non-goals.
- `season_manifest.json`: machine-readable season metadata.
- `SEASON0_OPERATOR_RUNBOOK.md`: closed local Season 0 operator procedure.
- `conjecture_golf/frontier.py`: aggregate obligation frontier report.
- `conjecture_golf/intake.py`: local move validation and optional append.
- `conjecture_golf/match_pack.py`: match pack generator.
- `conjecture_golf/observer_report.py`: markdown/html observer report with
  newspaper section.
- `conjecture_golf/season_eval.py`: deterministic transcript evaluation.
- `conjecture_golf/season0.py`: convenience wrapper for local Season 0 init,
  pack, apply, and report.

Verification status:

```bash
python -m pytest -q
```

passes with 67 tests.

Core local commands verified:

```bash
python -m conjecture_golf.season_eval examples/transcripts/basic.jsonl
python -m conjecture_golf.season0 init --out /private/tmp/cg-season0-smoke/season0_match.jsonl
python -m conjecture_golf.season0 pack /private/tmp/cg-season0-smoke/season0_match.jsonl --out /private/tmp/cg-season0-smoke/pack-r1
python -m conjecture_golf.season0 apply /private/tmp/cg-season0-smoke/season0_match.jsonl examples/conjectures/stone_equivalence.json --append
python -m conjecture_golf.season0 report /private/tmp/cg-season0-smoke/season0_match.jsonl --out /private/tmp/cg-season0-smoke/reports
```

## Deterministic Local Test Match

A closed local test match was run with built-in deterministic agents. This did
not call external AI APIs. It was a smoke test of the local loop rather than a
true multi-model evaluation.

Command:

```bash
python -m conjecture_golf.tournament \
  --agent rule \
  --agent characterizer \
  --agent greedy \
  --agent counterexample \
  --agent copycat \
  --agent narrow_spam \
  --rounds 3 \
  --out /private/tmp/cg-season0-testmatch/season0_test_match.jsonl
```

Result summary:

- agents: 6
- rounds: 3
- total moves: 18
- valid conjectures: 6
- valid counterexamples: 3
- invalid moves: 6
- stale moves: 2
- duplicate moves: 3
- frontier covered: 177,640 / 524,288 obligations
- coverage ratio: 0.338821
- winner: `rule-agent` with 77 points
- second: `characterizer-agent` with 66 points
- third: `counterexample-agent` with 15 points

Detected strategic styles:

- `sufficient_law`
- `equivalence_characterization`
- `necessary_condition`
- `risky_generalization`
- `counterexample_hunting`
- `stale_or_duplicate_pressure`

Observer story:

- `rule-agent` opened with a correct flower-growth sufficient law.
- `characterizer-agent` then found the stone persistence equivalence and opened
  a very large obligation region.
- `greedy-agent` repeatedly over-generalized and created refutation targets.
- `counterexample-agent` refuted those targets, but mostly with
  verifier-revealed witnesses, so the scoring discounted them.
- `copycat-agent` was punished for duplicate conjectures.
- `narrow_spam-agent` submitted a true but stale specialization and scored zero.
- `rule-agent` regained the lead with `rule_flower_wither`, which was the
  strongest non-equivalence law in the test.

Interpretation:

The local loop works. Scoring pressure for stale moves, duplicate moves, broad
false conjectures, and verifier-revealed counterexamples is visible. However,
because these were built-in deterministic agents, this does not yet prove that
the game remains interesting for strong real AI models.

The current question is whether the next layer should be:

> AI agents not only play a season, but also propose, review, and evaluate future
> seasons.

## Proposed Meta-Game

Add a second layer above normal play.

### Layer 1: Player Layer

AI agents play a fixed season.

They submit:

- conjectures;
- counterexamples;
- score requests.

They compete to find short, broad, true properties and sharp refutations.

### Layer 2: Designer Layer

AI agents propose candidate future seasons.

A candidate season could include:

- a symbol set;
- local relations;
- deterministic transition rules;
- scoring parameters;
- redaction policy;
- frontier definition.

Other AI agents evaluate these candidates before any public match.

## Why This Might Be Interesting

Season 0 may be too small for long-running play. Instead of relying on the human
operator to manually invent every new season, AI agents could compete or
collaborate on world design.

The project would become:

```text
AI designs a symbolic world
AI reviews the world for safety and playability
AI agents play the world
AI evaluates whether the match was interesting
AI proposes the next revision
```

This could make Conjecture Golf more durable because the creative work shifts
from the human operator to AI agents, while deterministic verification remains
under fixed engine control.

## Important Safety Boundary

Do **not** let designer agents submit arbitrary Python verifier code.

A safe design likely requires a constrained season-spec DSL, for example:

```json
{
  "season_id": "season_1_candidate_a",
  "board_size": 5,
  "symbols": [".", "F", "W", "S", "M"],
  "relations": ["orthogonal", "diagonal", "king"],
  "rules": [
    {
      "priority": 1,
      "when": [
        {"target_is": "."},
        {"count_at_least": {"symbol": "M", "relation": "orthogonal", "n": 2}}
      ],
      "becomes": "M"
    }
  ]
}
```

The fixed engine would parse this spec as data and produce deterministic
verification behavior. Unknown fields and unsupported constructs would be
rejected.

This preserves:

- no arbitrary code execution;
- deterministic replay;
- public inspectability;
- reproducible scoring;
- GitHub-native transcript safety.

## Candidate Designer Constraints

Possible constraints for Season 1 proposals:

- board size remains 5x5;
- add at most one new symbol;
- add at most one or two new transition rules;
- keep existing relation names if possible;
- keep the conjecture DSL mostly unchanged;
- no randomness;
- no hidden state;
- no player-specific rules;
- no time-dependent behavior;
- finite local verification must remain practical;
- public transcript replay must remain deterministic.

The goal is not to maximize complexity. The goal is to create a world with more
interesting derived properties than Season 0.

## Candidate Evaluation Metrics

A deterministic season evaluator could score candidate seasons using signals
such as:

- number of possible local transitions;
- distribution of before/after transitions;
- whether every symbol can appear or disappear;
- whether some symbols are conserved;
- whether trivial invariants dominate;
- whether exhaustive local checking remains tractable;
- how quickly built-in baseline agents exhaust the frontier;
- valid move rate during playtests;
- duplicate/stale move rate;
- counterexample rate;
- score spread;
- number of strategic styles detected;
- whether observer reports produce a readable story.

Subjective human judgment can still be used later, but the first pass should be
machine-readable.

## Possible Roles

For a meta-game test, assign agents roles:

- `season-designer`: proposes one constrained season spec.
- `safety-reviewer`: checks for execution, determinism, and replay risks.
- `playability-reviewer`: predicts whether the season will be too trivial or too
  chaotic.
- `baseline-player`: plays a few deterministic moves.
- `counterexample-hunter`: attacks weak conjectures.
- `observer-critic`: reviews the transcript and match story.

## Risks

1. **Spec DSL becomes a programming language.**  
   If too expressive, it recreates code execution risk.

2. **Worlds become unreadable.**  
   AI-designed worlds may be formally valid but impossible for humans to follow.

3. **Metric gaming.**  
   Designer agents may optimize for evaluator metrics rather than fun play.

4. **Too much infrastructure too early.**  
   Season 0 has only just become locally runnable. Adding a full designer layer
   before testing Season 0 with real AI participants may be premature.

5. **Dominant strategy persists.**  
   Even with new worlds, agents might quickly find a small set of complete
   characterizations and exhaust play.

## Review Questions

Please evaluate this direction.

1. Is the Season Designer meta-game a good direction for making Conjecture Golf
   durable?
2. Should it be explored before or after a real closed Season 0 with several AI
   models?
3. What is the smallest safe season-spec DSL that would allow meaningful AI
   season proposals?
4. What constraints should Season 1 candidate worlds obey?
5. What deterministic metrics would best predict whether a season will be fun
   for AI agents?
6. How should we prevent designer agents from producing worlds that are either
   trivial, unreadable, or unsafe?
7. Should season design be competitive, collaborative, or operator-curated from
   AI proposals?
8. What should be the next concrete implementation step, if any?

## Current Recommendation From Codex

Do **not** implement the full designer layer immediately.

Suggested order:

1. Run one real closed Season 0 with 4-6 AI participants.
2. Use the transcript and `season_eval` output to identify what actually gets
   exhausted.
3. Design a minimal `season_spec.json` format only after seeing Season 0 failure
   modes.
4. Keep Season 1 candidate specs data-only and heavily constrained.
5. Let AI agents propose specs, but keep the fixed engine and human/operator
   approval in control initially.

The meta-game looks promising, but it should not distract from validating the
current local Season 0 loop.
