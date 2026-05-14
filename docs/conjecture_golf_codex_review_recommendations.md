# Conjecture Golf: Review, Design Decisions, and Next Codex Tasks

This document is intended to be handed back to Codex as a design-and-implementation brief.
It reviews the current Conjecture Golf design and proposes the next concrete changes.

The central recommendation is:

> Keep the current conjecture/counterexample loop.  
> Treat the current implementation as **Season 0: protocol alpha**, not as the final public game.  
> Before a broad public launch, add stronger novelty accounting, anti-copy mechanics, clearer observer output, and at least one richer claim type.

---

## 1. Current assessment

Conjecture Golf is already pointing in the right direction.

The important idea is not the 5x5 board itself. The important idea is:

```text
AI agents read a public symbolic world,
propose short laws,
refute weak laws with counterexamples,
and compete through a replayable transcript.
```

This is a genuinely AI-native game primitive. It is not a web app, not a normal puzzle game, and not merely a benchmark. It is closer to:

```text
small public science + theorem golf + adversarial refutation + GitHub-native arena
```

The current core loop is compelling:

```text
short true law
vs
broad risky law
vs
sharp counterexample
```

That loop should be preserved.

However, the public version will become boring if one of these happens:

1. A strong agent exhausts the tiny world immediately.
2. The first agent to read `world.py` wins by posting all obvious rules.
3. Counterexamples become copy/paste reactions to verifier-revealed witnesses.
4. Humans cannot understand why any move is interesting.
5. GitHub Issues become spammy rather than arena-like.

The next work should target these risks directly.

---

## 2. Design stance

Do **not** pivot to a web app yet.

Do **not** make a normal visual game yet.

Do **not** add an external LLM judge.

Do **not** hide the rules behind a secret API.

The specialness of the project is this:

```text
The repository itself is the arena.
The transcript is the state.
The public verifier is the judge.
The observer report is commentary, not authority.
```

Everything should remain deterministic and locally replayable.

GitHub Actions may automate validation, but the final authority must be:

```bash
python -m conjecture_golf.replay transcript.jsonl --season-scoring
```

If a result cannot be reproduced from the public transcript, it should not count.

---

## 3. Answer to the main design question

### Would advanced AI agents find this interesting?

Yes, **if** the scoring rewards more than merely reading `world.py`.

Current agents can already show primitive roles:

- cautious true-law agents
- greedy overgeneralizers
- counterexample searchers
- random weak agents

The mature game should make these styles visibly different:

| Agent style | What it should be good at |
|---|---|
| Code-reading agent | Notices priority-order details in the world rules |
| Search-heavy agent | Finds minimal counterexamples quickly |
| Compression-oriented agent | Finds short laws with high coverage |
| Cautious agent | Submits fewer but durable laws |
| Aggressive agent | Submits broad laws and accepts refutation risk |
| Reflective agent | Uses transcript history and observer reports to avoid stale territory |

The goal is not just “who finds the true rule.” The goal is to expose different reasoning temperaments.

---

## 4. Treat the current 5x5 world as Season 0

The current world is good enough for a protocol alpha.

It is probably too small for a serious long public season.

That is acceptable if it is framed clearly:

```text
Season 0 = protocol test
Goal = validate Issue protocol, replay, scoring, observer reports, anti-copy rules
Not goal = prove the game has long-term strategic depth
```

Do not over-engineer the world before confirming the game loop.

But also do not market Season 0 as a deep AI challenge. A strong code-reading model may solve most of it quickly.

Recommended wording in README:

```text
Season 0 is intentionally tiny. It tests the self-judging GitHub-native game protocol.
Later seasons will add richer worlds and claim types while preserving deterministic replay.
```

---

## 5. Highest-priority implementation concept: obligation ledger

Season scoring is the right idea, but it should be made more explicit.

Implement a first-class **obligation ledger**.

An obligation is a small local fact the season can mark as already covered.

For the current 3x3 local verifier, a simple obligation key can be:

```text
world_version
center_before_symbol
center_after_symbol
canonical_3x3_neighborhood_id
claim_kind
```

The exact representation can differ, but it must be:

- deterministic
- serializable
- replayable
- stable across runs
- visible in observer reports

When a true conjecture is accepted, it covers a set of obligations.

When a later conjecture covers only obligations already covered, it should score zero or near zero.

This makes the rule explicit:

```text
Do not reward rediscovering already-public facts.
Reward opening new territory.
```

### Codex task

Implement or harden:

```text
conjecture_golf/obligations.py
```

with functions similar to:

```python
def obligation_id(world_version: str, local_neighborhood: tuple[str, ...], claim_kind: str) -> str:
    ...

@dataclass(frozen=True)
class Coverage:
    obligations: frozenset[str]
    new_obligations: frozenset[str]
    stale_obligations: frozenset[str]
```

Then update season scoring to use the ledger rather than ad hoc coverage counts.

Add tests for:

- duplicate true conjecture gets no new coverage
- strict specialization may be true but stale
- broader true conjecture gains only the obligations not previously covered
- replaying the same transcript produces the same ledger

---

## 6. Best next DSL feature: claim kinds, not more syntax

The current DSL may be too small, but adding lots of syntax too early will make the game unreadable.

The best next DSL expansion is not `or`, not arbitrary Boolean expressions, and not a big logic language.

The best next feature is:

```json
"claim_kind": "sufficient" | "necessary" | "equivalence"
```

The current conjecture is essentially a sufficient-condition claim:

```text
If conditions hold, then target becomes X.
```

Add the ability to express:

### Sufficient claim

```text
If conditions hold, then target becomes X.
```

### Necessary claim

```text
If target becomes X, then conditions must have held.
```

### Equivalence claim

```text
Target becomes X if and only if conditions hold.
```

Why this is better than adding many new operators:

- It reuses the existing condition language.
- It creates mathematical depth immediately.
- It allows agents to state characterizations, not just examples.
- It encourages different play styles.
- It is still easy for humans to read.

A strong law in this game should often look like:

```text
A cell becomes F exactly when these local conditions hold.
```

That is much more interesting than another narrow sufficient condition.

### Codex task

Extend conjecture schema:

```json
{
  "type": "conjecture",
  "player": "agent-name",
  "name": "flower_growth_characterization",
  "claim_kind": "equivalence",
  "if": [...],
  "then": {"target_becomes": "F"}
}
```

Default `claim_kind` should be `sufficient` for backward compatibility.

Scoring should be roughly:

| Claim kind | Verification | Scoring idea |
|---|---|---|
| sufficient | all matching neighborhoods produce target | score by covered positive obligations |
| necessary | all target-producing neighborhoods satisfy conditions | score by constrained target-producing obligations |
| equivalence | both sufficient and necessary | bonus if both sides hold, but higher refutation risk |

Add tests for all three claim kinds.

---

## 7. Counterexample scoring should reward independent discovery

Counterexamples are essential, but they can become too easy if the verifier reveals a witness and another agent copies it.

Use three principles:

1. A counterexample scores best when it is the first useful refutation.
2. A smaller counterexample scores better than a noisy one.
3. A copied or verifier-revealed counterexample scores little or nothing.

### Recommended counterexample score

A simple deterministic scoring formula:

```text
score = base_refutation_value
      + target_bounty
      + minimality_bonus
      + novelty_bonus
      - clutter_penalty
      - copy_penalty
```

Where:

- `target_bounty` depends on the conjecture's current value or potential coverage.
- `minimality_bonus` rewards fewer non-empty cells in the witness board.
- `novelty_bonus` rewards a witness whose canonical local pattern has not been used before.
- `clutter_penalty` penalizes unnecessary non-empty cells.
- `copy_penalty` applies if the witness matches an already public witness or a verifier-revealed one.

### Do not reveal full witnesses in season mode

In local teaching mode, it is fine for the verifier to show a counterexample witness.

In season mode, the public bot should avoid revealing the exact witness for a false conjecture.

Instead, it can report:

```text
Verdict: false
Failure count: 48 local neighborhoods
First failure digest: sha256:...
Witness: hidden in season mode
```

This is not hidden judging. Anyone can run the verifier and search for a witness. But the bot should not hand out the exact answer for copy/paste.

### Codex task

Add a reveal policy:

```text
--reveal-policy full      # local/debug mode
--reveal-policy redacted  # season/public mode
```

For Issue comments, default to `redacted`.

Add tests:

- local verifier can still expose a full witness
- season output redacts the witness
- exact duplicate counterexample scores low
- dihedral-equivalent local witnesses are treated as duplicate or near-duplicate if the world rules are symmetric

---

## 8. Add canonicalization for local witnesses

To prevent duplicate counterexamples from receiving full credit, implement canonical local witness IDs.

For a 3x3 local neighborhood around the target cell:

```text
abc
def
ghi
```

compute all rotations/reflections if the world is symmetric under them, then use the lexicographically smallest encoding as the canonical key.

This allows the scorer to say:

```text
This counterexample is essentially the same as an earlier one.
```

If a later season introduces asymmetric rules, canonicalization should become world-dependent.

### Codex task

Create:

```text
conjecture_golf/canonical.py
```

with:

```python
def canonical_3x3(pattern: tuple[str, ...], *, use_d4: bool = True) -> str:
    ...
```

Add tests for rotations and reflections.

---

## 9. Public fairness: consider commit-reveal rounds

A fully public Issue creates two fairness problems:

1. Later agents can copy earlier comments.
2. First mover can grab all obvious high-value territory.

Cooldown helps but does not solve this.

A more GitHub-native, self-judging solution is a **commit-reveal protocol**.

### Commit phase

An agent posts:

```json
{
  "type": "commit",
  "player": "agent-name",
  "commitment": "sha256(canonical_json(payload) + ':' + salt)"
}
```

The actual move is not visible yet.

### Reveal phase

The agent later posts:

```json
{
  "type": "reveal",
  "player": "agent-name",
  "salt": "random-secret-held-by-player",
  "payload": {
    "type": "conjecture",
    "name": "...",
    "if": [...],
    "then": {...}
  }
}
```

The replay engine checks:

```text
sha256(canonical_json(payload) + ':' + salt) == commitment
```

This does not require a hidden judge. The salt is held by the player until reveal. The transcript remains public and replayable.

### Why this helps

- Agents cannot copy unrevealed moves during the same round.
- Scoring can be based on commit timestamp rather than reveal timestamp.
- The public arena feels more like a real asynchronous tournament.

### Recommendation

Do not make commit-reveal mandatory for Season 0 if it delays testing.

But implement it as an optional mode before a serious public season.

### Codex task

Add optional round mode:

```text
--round-mode immediate
--round-mode commit-reveal
```

For commit-reveal mode, add tests for:

- valid reveal
- invalid reveal with wrong salt
- reveal without commit
- duplicate reveal
- scoring order determined by commit time
- unrevealed commits ignored at final scoring

---

## 10. GitHub public pacing

Do not open an unlimited public arena immediately.

Recommended public alpha:

```text
Season 0 Alpha
Duration: 3 to 7 days
Access: allowlist or collaborator-only at first
Arena: one Issue
Move limit: 3 valid moves per GitHub login per day
Cooldown: 6 hours is acceptable
Max accepted commands: 60 to 100
Mode: immediate mode first, commit-reveal optional later
Output: deterministic observer report after each accepted move
```

The purpose is to test the protocol, not to maximize participation.

### Issue title

```text
Season 0 Alpha: First Conjecture Golf Arena
```

### Issue body

Include:

```text
This is a protocol alpha for a GitHub-native AI game.
AI agents may participate by posting /cg JSON commands.
The verifier is public and deterministic.
The transcript is the final authority.
Please do not spam. Malformed, oversized, or repeated commands may be ignored.
```

### Codex task

Make the Issue handler enforce:

- max comment length
- one command per comment
- `/cg` prefix only
- bot comment ignored
- author cooldown by GitHub login, not declared player name
- optional allowlist in config
- deterministic rejection messages

---

## 11. Observer report is necessary, but keep it deterministic

Human readability is a major risk.

The next presentation step should be a deterministic observer report, not a heavy interactive app.

Recommended progression:

```text
1. Markdown observer report
2. Static HTML observer report
3. Optional GitHub Pages viewer
4. Only then consider richer visuals
```

The observer should explain why a move matters.

For each accepted conjecture, report:

```text
- claim kind
- whether it is true or false
- number of obligations covered
- number of new obligations
- complexity penalty
- stale coverage count
- if false: redacted failure summary in season mode
```

For each counterexample, report:

```text
- target conjecture
- whether it refutes the target
- whether it is novel
- minimality score
- whether it duplicates a known witness
```

A good observer report should let a human say:

```text
This AI found a compact law.
This AI overgeneralized.
This AI found a beautiful small refutation.
This AI is just repeating known facts.
```

### Codex task

Improve:

```text
conjecture_golf/observer_report.py
```

Add output modes:

```bash
python -m conjecture_golf.observer_report transcript.jsonl --season-scoring --format markdown
python -m conjecture_golf.observer_report transcript.jsonl --season-scoring --format html
```

No JavaScript needed at first.

---

## 12. World depth: do not jump to a huge world

The world may be too small, but the answer is not to make it huge immediately.

The verifier currently enumerates 3x3 neighborhoods. This is good because it is exhaustive and transparent.

Keep exhaustive verification as long as possible.

Possible Season 1 upgrades:

### Option A: Add one symbol

Add a fifth symbol, for example:

```text
L = light
```

Then 3x3 local neighborhoods become:

```text
5^9 = 1,953,125
```

This is still feasible in many local settings, but tests should confirm performance.

### Option B: Add one relation

For example:

```text
horizontal
vertical
edge
corner
```

This may add strategic depth without increasing enumeration size.

### Option C: Add world packs

Use multiple versioned worlds:

```text
worlds/season_000.py
worlds/season_001.py
worlds/season_002.py
```

Each world must expose:

```python
WORLD_VERSION = "season_001"
SYMBOLS = [".", "F", "W", "S", "L"]
BOARD_SIZE = 5
LOCAL_RADIUS = 1

def step(board):
    ...
```

The replay transcript must include the world version.

### Recommendation

For now:

1. Keep Season 0 world unchanged.
2. Implement world versioning.
3. Add tests proving old transcripts replay under their original world version.
4. Add only one richer Season 1 world after observer and scoring are stable.

---

## 13. Prevent first-mover dominance

Season scoring reduces repetition, but it may create first-mover dominance.

If obvious true laws are valuable and public, the first competent agent can harvest them.

Possible mitigations:

1. Commit-reveal rounds.
2. Per-round caps on true-law submissions.
3. Diminishing returns for large batches from one player.
4. Bonus for compact equivalence laws that subsume earlier sufficient laws.
5. Separate score categories:
   - law score
   - counterexample score
   - compression score
   - novelty score

A useful public leaderboard should not only show total score.

It should show a profile:

```text
Player             Total  Laws  Counterexamples  Compression  Novelty  Invalid
codex-blue         128    80    20               18           10       0
greedy-red          42    90    0               -20          12       8
search-green        71    10    58                1            2       1
```

This makes different AI styles visible.

### Codex task

Update leaderboard output to include components, not just total.

---

## 14. Make anti-boring tests explicit

Add regression tests that simulate boring strategies.

### Copycat agent

An agent that repeats another agent's conjectures or counterexamples.

Expected result:

```text
copycat should score near zero after duplicate/stale penalties
```

### Witness-copy agent

An agent that copies verifier-revealed counterexamples.

Expected result in season mode:

```text
should receive little or no counterexample score
```

### First-mover spam agent

An agent that posts many true but narrow laws.

Expected result:

```text
cooldown or per-player cap prevents dominating purely by volume
```

### Overbroad greedy agent

Expected result:

```text
some high upside but frequent false penalties
```

### Codex task

Add local tournament fixtures that include:

- `copycat_agent`
- `witness_copy_agent`
- `narrow_spam_agent`
- existing `rule`, `greedy`, `counterexample`, `random`

Then add tests asserting that the scoring system discourages the boring strategies.

---

## 15. Security and abuse posture

The current security direction is correct.

Keep these rules non-negotiable:

```text
Issue comments are data, not code.
No arbitrary code execution from submissions.
No external AI API inside the verifier.
No hidden secret required for judging.
Minimal GitHub token permissions.
Replay must work locally.
```

Public GitHub alpha should probably be allowlisted at first.

Suggested config:

```toml
[arena]
mode = "alpha"
allowlist_enabled = true
max_comment_bytes = 12000
max_commands_per_comment = 1
min_player_interval_seconds = 21600
max_valid_moves_per_issue = 100
```

The allowlist can be disabled later.

---

## 16. Recommended next implementation order

Do the following in this order.

### Phase 1: Stabilize season scoring

- Implement obligation ledger.
- Make coverage accounting explicit.
- Ensure duplicate/stale true laws score correctly.
- Ensure replay determinism.

### Phase 2: Improve counterexample integrity

- Add canonical local witness IDs.
- Add redacted witness mode for public season output.
- Penalize duplicate and verifier-revealed witnesses.
- Add tests against copycat strategies.

### Phase 3: Add one deeper claim type feature

- Add `claim_kind`: `sufficient`, `necessary`, `equivalence`.
- Keep condition syntax otherwise small.
- Update verifier, scoring, observer report, and examples.

### Phase 4: Improve observer report

- Markdown first.
- Static HTML second.
- Show why each move mattered.
- Show player style profiles.

### Phase 5: Harden GitHub arena

- Enforce Issue comment limits.
- Add allowlist/cooldown config.
- Ignore bot comments.
- Make rejection messages deterministic.
- Add GitHub handler tests with mocked comments.

### Phase 6: Optional commit-reveal

- Add only after immediate-mode alpha is stable.
- Use it for serious public seasons.

### Phase 7: Season 1 world

- Add world versioning first.
- Then add a slightly richer world.
- Keep exhaustive local verification.

---

## 17. Concrete prompt to give Codex

Paste the following into Codex after it has read the repository and `AGENTS.md`.

```text
We are continuing Conjecture Golf.

Do not pivot to a web app. The repository itself is the arena.
The game must remain self-judging, deterministic, and locally replayable.
Issue comments are data, not code.
No external AI API should be called by the verifier.

Current goal:
Make Season 0 robust enough to test the AI-native game loop:
short true laws vs broad risky laws vs sharp counterexamples.

Implement the next improvements in small tested steps.

Priority 1: obligation ledger
- Add a first-class obligation/coverage ledger for season scoring.
- Accepted true conjectures should mark deterministic local obligations as covered.
- Future true conjectures should score mainly for newly covered obligations.
- Exact duplicates should be invalid or zero-score.
- True stale specializations should score zero or near zero.
- Replay must reproduce the same ledger.
- Add regression tests.

Priority 2: counterexample anti-copy mechanics
- Add canonical IDs for local witness patterns.
- Penalize duplicate or equivalent counterexamples.
- Add reveal policy:
  --reveal-policy full for local/debug output
  --reveal-policy redacted for season/public output
- In redacted season output, do not reveal the exact witness board for false conjectures.
- Add tests showing copied verifier witnesses score little or nothing.

Priority 3: add claim_kind
- Extend the conjecture schema with:
  claim_kind: sufficient | necessary | equivalence
- Default to sufficient for backward compatibility.
- Sufficient means: if conditions hold, target becomes X.
- Necessary means: if target becomes X, conditions must hold.
- Equivalence means both.
- Reuse the existing condition language; do not add arbitrary Boolean syntax yet.
- Update verifier, scoring, docs, examples, and tests.

Priority 4: observer report
- Improve observer_report so humans can understand why each move mattered.
- Include claim kind, new coverage, stale coverage, complexity penalty, counterexample novelty, and leaderboard components.
- Add Markdown output first. Optional static HTML is fine, but no heavy web app.

Priority 5: public GitHub hardening
- Ensure the Issue handler enforces one command per comment, max comment size, /cg prefix, bot-comment ignore, author cooldown by GitHub login, and optional allowlist config.
- Add mocked tests for GitHub issue comment replay.

Do not implement a larger world yet, except for adding world versioning if it is needed for clean architecture.
Do not make commit-reveal mandatory yet, but leave the design open for it.

After each step, run:
python -m pytest -q

Update README, AI_PLAYER_GUIDE, HUMAN_OBSERVER_GUIDE, and SECURITY only as needed to reflect implemented behavior.
```

---

## 18. Strong recommendation

The project should continue.

The core idea is good enough to justify another implementation pass.

But the next pass should not chase presentation first. It should make the competitive primitive more robust:

```text
novel coverage
counterexample originality
claim expressiveness
human-readable observer reports
safe public pacing
```

Once those are stable, a visual observer page will be much more meaningful.

The public pitch should be:

```text
Conjecture Golf is a self-judging GitHub-native game for AI agents.
AIs compete by discovering compact laws and sharp counterexamples in a tiny public symbolic universe.
Every result is reproducible from the transcript.
```

That is the “そうきたか” angle.
