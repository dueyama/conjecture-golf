# Conjecture Golf V2: Design Review and Next Codex Instructions

Date: 2026-05-14

This memo responds to `GPT_PRO_REVIEW_BRIEF_V2.md`. It is intended to be pasted back into Codex or kept as a project decision note.

---

## 0. Executive decision

My recommendation is:

> **Do not expand the world yet. Do not implement commit-reveal yet. Do not add more claim kinds yet.**
>
> The next step should be a **closed local multi-model Season 0 test** plus a small set of instrumentation features that make the test measurable.

The current implementation has crossed an important threshold. It is no longer just a toy verifier. It now has:

- memory, via the obligation ledger;
- claim asymmetry, via `sufficient`, `necessary`, and `equivalence`;
- anti-copy mechanics, via canonical witnesses and redaction;
- human-facing output, via Markdown/HTML observer reports;
- anti-boring regression agents;
- replayable deterministic scoring.

That is enough to test the real thesis:

> **Do different advanced AI models develop visibly different conjecture/refutation styles in this game?**

Until that is tested, further rule design is mostly speculation.

---

## 1. Answer to the main design questions

### 1. Does current season scoring sufficiently prevent boring copycat play?

**For closed Season 0: yes. For broad public launch: not yet.**

The current scoring is now strong enough to prevent the most obvious boring strategies:

- repeating true conjectures;
- submitting stale narrow specializations;
- copying verifier-revealed witnesses;
- farming already-refuted conjectures.

The important change is that the game now has memory. A move must be evaluated relative to the public transcript, not in isolation.

However, for a public GitHub arena, there will be new boring strategies:

- many near-duplicate accounts or agents;
- prompt-injected junk commands;
- mechanical enumeration of the whole DSL space;
- tiny score farming around edge cases;
- comments designed to be annoying rather than strategic.

So the current mechanics are adequate for **closed local multi-model testing** and maybe **collaborator-only alpha**, but not yet for a fully open public repo.

Codex should not solve public abuse yet. It should add diagnostics that tell us whether boring strategies still dominate in controlled testing.

---

### 2. Are `sufficient`, `necessary`, and `equivalence` the right first claim kinds?

**Yes. Keep exactly these three for Season 0.**

They are conceptually clean:

- `sufficient` = a local cause implies an outcome;
- `necessary` = an outcome requires a local condition;
- `equivalence` = an exact characterization.

This is a good first triad because it gives distinct strategic identities:

- law-finding agents will prefer `sufficient`;
- characterization agents will prefer `necessary` and `equivalence`;
- aggressive agents will overgeneralize and become refutation targets.

Do **not** add implication chains, quantifiers over multiple target cells, disjunctions, temporal operators, or multi-step claims yet. Those may make the DSL feel more mathematical, but they will also make the first public explanation much harder.

Season 0 should ask: can AI agents play interestingly with this small triad?

---

### 3. Is the obligation ledger a good representation of escalating difficulty?

**Yes. This is probably the most important structural improvement in V2.**

The obligation ledger turns the game from isolated puzzle submissions into a season.

The right mental model is:

> Each accepted conjecture claims territory in a finite theorem map. Later agents must find uncovered territory or better characterizations.

This is exactly what makes the transcript worth reading. Without the ledger, an AI can play each move as if history does not matter. With the ledger, the game becomes:

- read the current theory;
- find what is missing;
- decide whether to add a law, an equivalence, or a refutation;
- avoid stale territory.

The ledger should be made more visible. I recommend adding an **obligation frontier report** rather than expanding the DSL.

---

### 4. Is equivalence currently over-rewarded, under-rewarded, or about right?

**Probably slightly over-rewarded in principle, but do not tune it yet. Instrument it first.**

Equivalence should be valuable because it is cognitively harder: it proves both directions. But it can become too strong if obvious equivalences receive large rewards simply because they cover both sufficient and necessary obligations.

Recommended policy for now:

1. Keep current equivalence scoring for the closed test.
2. Add diagnostics that split equivalence reward into:
   - sufficient-side newly covered obligations;
   - necessary-side newly covered obligations;
   - stale obligations;
   - complexity penalty;
   - any equivalence bonus.
3. After the closed test, inspect whether equivalence wins because it is genuinely informative or because it double-counts trivial territory.

Potential later scoring rule:

```text
equivalence_score = sufficient_new + necessary_new + closure_bonus - complexity_penalty

closure_bonus is paid only when both sides cover nontrivial new territory.
```

Also consider a cap:

```text
equivalence_score <= 1.5 * max(score_as_sufficient, score_as_necessary)
```

But do not implement this cap before collecting data.

---

### 5. How should counterexamples score?

Counterexamples should score by a combination of:

1. **target value**: refuting an important, high-scoring, broad conjecture should matter;
2. **originality**: duplicate local patterns should score little;
3. **minimality**: smaller, cleaner witnesses should score more;
4. **timing**: the first valid refutation should be worth more than later refutations.

Recommended conceptual weighting:

```text
counterexample_score =
    0.40 * target_value
  + 0.35 * originality
  + 0.20 * minimality
  + 0.05 * timing_bonus
```

In Season 0, avoid making minimality too dominant. If minimality dominates, the game becomes a compression contest over witnesses rather than a conjecture/refutation game.

Current D4 canonicalization is enough for Season 0. A richer notion such as “minimal supporting cells” is desirable later, but it is not necessary before the closed multi-model test.

Future feature:

```text
minimal_support_signature(witness)
```

This would remove irrelevant cells from a counterexample and canonicalize the reduced pattern. That is better than raw D4 on the full 3x3 witness, but it is a Season 1 improvement.

---

### 6. Should public Season 0 use redacted witnesses by default?

**Yes. Public and closed competitive views should use redacted witnesses by default.**

Use two views:

- `debug_view`: full witnesses, for local development and tests;
- `player_view`: redacted witnesses, for agents during a match;
- `observer_view`: optionally reveal full witnesses only after a match is over.

This preserves determinism while avoiding the “verifier hands out a free counterexample” failure mode.

Codex should make sure this policy is explicit in the docs and CLI names.

---

### 7. Is immediate-mode with cooldown enough for alpha, or is commit-reveal needed?

**Immediate-mode is enough for closed Season 0 and collaborator-only alpha. Commit-reveal should wait.**

Commit-reveal adds protocol complexity:

- two-phase submissions;
- unresolved commitments;
- missed reveal windows;
- digest validation;
- confusing observer reports;
- more ways for participants to make invalid moves.

The first test should be simple:

```text
AI sees transcript -> submits 1 or 2 moves -> replay -> report
```

If simultaneous fairness becomes important later, I would first implement **round batching** before full commit-reveal:

```text
Round N opens.
Each player submits at most one move privately to the experiment runner.
Runner appends all moves in deterministic randomized order.
Replay.
Round N+1 opens.
```

For GitHub-native public play, commit-reveal can be a Season 1 or Season 2 feature.

---

### 8. What one feature would most improve strategic depth without making the DSL harder?

Add an **obligation frontier report**.

This is not a DSL feature. It is a season-state feature.

The report should answer:

- Which claim kinds have the most uncovered obligations?
- Which transitions are underexplored? For example `. -> F`, `F -> .`, `W -> .`, etc.
- Which target symbols and before/after pairs have high remaining value?
- Which previous claims created stale traps?
- Which conjecture shapes are currently overused?

This gives AI players strategic direction without making the language more complex.

Example output:

```text
Obligation Frontier
-------------------
High-value uncovered areas:
1. necessary claims for . -> W
2. equivalence claims around W evaporation
3. sufficient claims involving stone blockers
4. refutations of broad flower-growth claims

Stale traps:
- target_is S -> S is mostly covered
- simple . -> F sufficient laws are mostly covered
```

This is the best next feature because it makes “reading the season” part of the game.

---

### 9. What one feature would most improve human observability?

Add a **match newspaper page** to the static HTML report.

Not a web app. Not interactivity. Just a better deterministic static report.

The top of the HTML report should summarize the match as if it were a small scientific tournament:

- headline;
- final leaderboard;
- most valuable conjecture;
- sharpest counterexample;
- biggest failed overgeneralization;
- most stale move;
- key turning point;
- open frontier after the match;
- one-paragraph narrative.

Example:

```text
Match headline:
Characterizer-agent nearly caught rule-agent with a high-value equivalence,
but rule-agent won by opening more fresh sufficient territory.

Key turning point:
Greedy-agent proposed a broad flower-growth law, which became a refutation target.
Counterexample-agent found a novel witness, but witness redaction prevented cheap copycat farming.
```

This will make the game readable to humans without changing the core rules.

---

### 10. Is it ready for a closed local multi-model test?

**Yes. It is ready for a closed local multi-model test.**

Do not do another large design pass first.

The test should be explicitly framed as an experiment, not a product launch.

The key experimental question:

> Do different models produce distinct styles, or do they all converge on the same obvious claims?

If they produce distinct styles, the project is worth pushing toward a GitHub alpha.

If they do not, the next step is not presentation. The next step is a richer world or better season-state incentives.

---

## 2. Recommended closed local multi-model protocol

Use this protocol before adding major features.

### Participants

Use 3 to 5 AI participants, for example:

- Codex / GPT-style code-reading agent;
- another LLM with strong reasoning;
- a search-heavy local baseline;
- a deliberately greedy/broad baseline;
- a cautious law-only baseline.

### Materials given to each model

Each model receives:

- `AI_PLAYER_GUIDE.md`;
- `world.py`;
- `dsl.py` or DSL docs;
- current public transcript;
- current redacted observer report;
- current obligation frontier report, if implemented.

Do not give private debug witnesses.

### Round format

For the first experiment:

```text
Round count: 3
Moves per model per round: 1 or 2
Mode: immediate local transcript, not GitHub
Witness reveal policy: redacted
Scoring: --season-scoring
Postgame: each model writes a short commentary
```

### What to measure

Track:

- total score;
- law score;
- counterexample score;
- invalid penalty;
- new obligations covered;
- stale obligations attempted;
- false conjecture rate;
- average conjecture complexity;
- equivalence reward breakdown;
- counterexample originality;
- counterexample minimality;
- time/order sensitivity;
- style notes.

### What counts as success

The test succeeds if models visibly differ, for example:

- one model finds compact true laws;
- one model finds a broad but false conjecture;
- one model refutes with a sharp witness;
- one model identifies stale territory and avoids it;
- one model writes a useful postgame analysis.

The test fails if:

- all models submit the same obvious conjectures;
- the built-in rule-agent dominates advanced models;
- all counterexamples are trivial;
- equivalence always wins by obvious double-counting;
- the observer report is too dry to understand the match.

---

## 3. What Codex should implement next

Codex should implement measurement and test harnesses, not bigger rules.

### Priority A: season diagnostics

Add structured score explanations.

For every move, expose:

```json
{
  "move_index": 12,
  "player": "agent-name",
  "type": "conjecture",
  "claim_kind": "equivalence",
  "score": 42,
  "components": {
    "new_sufficient_obligations": 12,
    "new_necessary_obligations": 8,
    "stale_obligations": 17,
    "complexity_penalty": 3,
    "equivalence_bonus": 5
  }
}
```

For counterexamples:

```json
{
  "move_index": 18,
  "player": "agent-name",
  "type": "counterexample",
  "score": 16,
  "components": {
    "target_value": 10,
    "originality": 5,
    "minimality": 1,
    "duplicate_penalty": 0,
    "already_countered_penalty": 0,
    "verifier_revealed_penalty": 0
  }
}
```

This is essential before tuning.

---

### Priority B: obligation frontier report

Add:

```text
conjecture_golf/frontier.py
```

CLI:

```bash
python -m conjecture_golf.frontier transcript.jsonl --season-scoring --format markdown
python -m conjecture_golf.frontier transcript.jsonl --season-scoring --format json
```

The report should show:

- uncovered obligation counts by claim kind;
- uncovered obligation counts by before/after symbol pair;
- top stale traps;
- most-covered areas;
- suggested high-value areas, stated mechanically, not with AI prose.

This report should be safe to give to players.

---

### Priority C: closed match pack generator

Add:

```text
conjecture_golf/match_pack.py
```

CLI:

```bash
python -m conjecture_golf.match_pack \
  --transcript current.jsonl \
  --out /tmp/conjecture_golf_match_pack \
  --reveal-policy redacted
```

It should produce:

```text
match_pack/
  AI_PLAYER_GUIDE.md
  WORLD_SUMMARY.md
  DSL_REFERENCE.md
  CURRENT_TRANSCRIPT.jsonl
  OBSERVER_REPORT.html
  OBSERVER_REPORT.md
  FRONTIER_REPORT.md
  FRONTIER_REPORT.json
  SUBMISSION_TEMPLATE_CONJECTURE.json
  SUBMISSION_TEMPLATE_COUNTEREXAMPLE.json
```

This makes it easy to hand the same state to multiple models.

---

### Priority D: local move intake

Add:

```text
conjecture_golf/intake.py
```

CLI:

```bash
python -m conjecture_golf.intake \
  --transcript current.jsonl \
  --move proposed_move.json \
  --player model-a \
  --append
```

It should:

- validate the move;
- reject invalid schema;
- optionally attach metadata;
- append to transcript only if requested;
- print the immediate verdict;
- never execute code.

This is useful for manually running a closed multi-model test.

---

### Priority E: match newspaper section in observer report

Improve `observer_report` with a top summary:

- final leaderboard;
- best law;
- best equivalence;
- sharpest counterexample;
- biggest failed conjecture;
- most stale move;
- strategic frontier after match;
- one-paragraph deterministic narrative.

Keep it deterministic. Do not call an LLM from the engine.

---

## 4. What Codex should not do yet

Do **not** implement these before the closed test:

- commit-reveal;
- a larger Season 1 world;
- more claim kinds;
- multi-step temporal claims;
- a real web app;
- external AI API calls;
- automatic public GitHub launch;
- automatic README leaderboard commits;
- arbitrary participant code execution.

These may be useful later, but they add complexity before we know whether the core game is compelling.

---

## 5. Suggested Codex prompt

Paste this to Codex:

```text
We have implemented Conjecture Golf V2 with claim kinds, obligation ledger, witness redaction, anti-copy mechanics, local tournament runner, and observer reports.

Do not expand the world, do not add commit-reveal, and do not add new claim kinds yet.

The next goal is to prepare a closed local multi-model Season 0 test.

Implement the following:

1. Season scoring diagnostics
   - For every move, expose structured score components.
   - For equivalence conjectures, split newly covered sufficient-side and necessary-side obligations.
   - For counterexamples, split target value, originality, minimality, duplicate penalty, already-countered penalty, and verifier-revealed penalty where those concepts already exist.
   - Add tests proving these diagnostics are deterministic under replay.

2. Obligation frontier report
   - Add conjecture_golf/frontier.py.
   - CLI:
       python -m conjecture_golf.frontier transcript.jsonl --season-scoring --format markdown
       python -m conjecture_golf.frontier transcript.jsonl --season-scoring --format json
   - Report uncovered obligations by claim_kind and before/after symbol pair.
   - Report stale traps and over-covered areas.
   - Keep output deterministic and safe to show to players.

3. Match pack generator
   - Add conjecture_golf/match_pack.py.
   - CLI:
       python -m conjecture_golf.match_pack --transcript current.jsonl --out match_pack --reveal-policy redacted
   - Generate:
       AI_PLAYER_GUIDE.md
       WORLD_SUMMARY.md
       DSL_REFERENCE.md
       CURRENT_TRANSCRIPT.jsonl
       OBSERVER_REPORT.html
       OBSERVER_REPORT.md
       FRONTIER_REPORT.md
       FRONTIER_REPORT.json
       SUBMISSION_TEMPLATE_CONJECTURE.json
       SUBMISSION_TEMPLATE_COUNTEREXAMPLE.json

4. Local intake tool
   - Add conjecture_golf/intake.py.
   - CLI:
       python -m conjecture_golf.intake --transcript current.jsonl --move proposed_move.json --player model-a --append
   - Validate the move, print a verdict, and optionally append to the transcript.
   - Do not execute code from submissions.

5. Observer report improvement
   - Add a deterministic match newspaper section at the top of the Markdown and HTML reports.
   - Include final leaderboard, best law, best equivalence, sharpest counterexample, biggest failed conjecture, most stale move, and open frontier summary.

Constraints:
- Keep everything deterministic.
- Do not call external AI APIs.
- Do not weaken the verifier.
- Do not remove redaction.
- Do not add public GitHub deployment behavior yet.
- Run pytest before finishing.
```

---

## 6. Final recommendation

This project is now at the right point for an experiment.

The next milestone should not be:

```text
Make it bigger.
```

It should be:

```text
Make one controlled match legible enough that we can tell whether AIs actually play differently.
```

If the answer is yes, then Conjecture Golf has something genuinely unusual:

> a game whose natural players are AI agents, whose board is a repository, whose moves are conjectures, and whose spectators watch small theories evolve.

That is the “そうきたか” part.
