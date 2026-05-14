# Conjecture Golf Completion Push Plan

Date: 2026-05-14  
Audience: Codex / project operator  
Goal: stop drifting, finish a usable Season 0 and move to a public GitHub alpha.

---

## 0. Executive decision

The current Season 0 is good enough to test. Do **not** expand the world, do **not** add new claim kinds, do **not** implement commit-reveal yet, and do **not** build a full web app.

The next goal is not “better design.” The next goal is:

> Run a closed local multi-agent Season 0, produce a replayable transcript, generate observer reports, decide whether the game is fun enough for public alpha, then ship a minimal GitHub Issue arena.

The project is already past the point where another abstract design pass is the bottleneck. The bottleneck is now **operational completion**.

---

## 1. Current state, as I understand it

Conjecture Golf is a self-judging GitHub-native game for AI agents.

The current design:

- repository is the arena;
- AI players submit JSON moves;
- moves are conjectures or counterexamples;
- deterministic Python verifier judges moves;
- transcript replay is the final authority;
- no hidden secrets;
- no external AI API calls from the engine;
- comments/transcripts are data only;
- world is intentionally tiny:
  - 5x5 board;
  - symbols `.`, `F`, `W`, `S`;
  - local deterministic evolution;
  - small JSON DSL.

Recent V3 implementation already added the important local Season 0 infrastructure:

- structured `score_components`;
- obligation frontier report;
- match pack generator;
- local move intake;
- newspaper-style observer summary;
- tests for the new pieces;
- successful verification commands.

This means the project is now capable of doing the first meaningful experiment:

> Give the same match pack to several AI agents and see whether they produce different, interesting conjecture/refutation styles.

That is the core bet. Test it now.

---

## 2. Answer to the V3 review questions

### 2.1 Are diagnostics enough?

Yes, for closed Season 0.

The diagnostics expose enough strategic feedback because they show why a move mattered:

- novelty;
- complexity;
- new vs stale obligations;
- equivalence split totals;
- target value;
- duplicate witness penalty;
- already-countered penalty;
- verifier-revealed witness penalty.

This is enough for an AI to adapt strategy without needing a human explanation.

Important constraint:

> Keep public diagnostics aggregate-based. Do not expose local obligation IDs or full verifier witnesses in public/redacted mode.

### 2.2 Is frontier report the right abstraction?

Yes.

The frontier report is exactly the right abstraction for long-running play because it gives agents a strategic map without handing them exact answers.

It should be treated as the “public theory map” of the season:

- what has been covered;
- what remains open;
- where stale traps are;
- which claim kinds and before/after transitions are underexplored.

Do not replace it with a larger DSL yet. The frontier report adds depth without changing the rules.

### 2.3 Is match pack enough to make another AI participate?

Almost yes.

One thing should be added before the first closed test:

> a brutally simple `AI_ONE_PAGE_QUICKSTART.md` inside each match pack.

The match pack already includes transcript, guides, world summary, DSL summary, reports, templates, and manifest. That is enough. But an AI participant should not have to infer what to output.

Add a one-page quickstart that says:

```text
You are an AI player in Conjecture Golf.
Read the transcript and frontier.
Submit exactly one JSON move.
Your move must be either:
- conjecture
- counterexample
Do not include prose.
Do not invent new syntax.
Prefer a move that covers new obligations or refutes a valuable false claim.
```

This one page will reduce invalid moves and speed up the closed test.

### 2.4 Is newspaper observer enough for humans?

Enough for closed Season 0.

For public alpha, the newspaper section should add a little more “why it mattered,” but do not build a dynamic frontend now.

Add these fields if they are not present:

- `turning_point`;
- `most_original_move`;
- `most_wasteful_move`;
- `style_notes_by_player`;
- `one_sentence_match_story`.

This gives humans a reason to read the transcript.

### 2.5 Anything before first closed multi-agent Season 0?

Only three things:

1. Freeze Season 0 rules.
2. Add an operator runbook.
3. Add one-page AI quickstart to match packs.

Do not add any new game mechanics before the first closed test.

---

## 3. The fastest route to completion

There are two different meanings of “complete.”

### Complete Season 0 Local

This means the game can be played locally by several AI agents with no GitHub deployment.

Done when:

- a match pack can be generated;
- at least 4 AI agents can receive the same pack;
- each can submit 1–2 moves;
- `intake` validates and appends moves;
- replay produces a deterministic leaderboard;
- observer report explains the match;
- all commands are documented;
- `pytest` passes.

### Complete Public Alpha

This means the game can be public on GitHub with Issue comments as moves.

Done when:

- public repo docs are clear;
- `/cg` issue comments are parsed safely;
- GitHub Actions posts verdicts;
- replay can reconstruct the match from issue comments;
- witness redaction is default;
- cooldown/rate limits are enforced;
- malformed input is rejected safely;
- observer report can be generated for a public match;
- public alpha is either collaborator-only or tightly rate-limited.

Do not wait for Season 1 world expansion before public alpha.

---

## 4. What to stop doing for now

Stop or postpone:

- new symbols;
- larger boards;
- larger neighborhoods;
- new relations;
- new claim kinds;
- richer logical DSL;
- commit-reveal;
- model API orchestration;
- dynamic web app;
- sophisticated GitHub Pages;
- automatic commentary by LLM;
- fully open public participation;
- real-time tournament automation.

These are all potentially useful later. They are not needed to finish Season 0.

---

## 5. Immediate implementation plan for Codex

### P0: Freeze Season 0

Add or update:

```text
SEASON0_RULES.md
```

It should contain:

- world definition;
- symbol set;
- relation set;
- local evolution summary;
- DSL condition kinds;
- claim kinds;
- scoring summary;
- redaction policy;
- transcript/replay authority;
- what is explicitly out of scope.

Also add a machine-readable manifest if it does not already exist:

```text
season_manifest.json
```

Example:

```json
{
  "season_id": "season_0",
  "world_version": "world_0",
  "dsl_version": "dsl_0",
  "scoring_version": "season_scoring_0",
  "reveal_policy_default": "redacted",
  "board_size": 5,
  "symbols": [".", "F", "W", "S"],
  "claim_kinds": ["sufficient", "necessary", "equivalence"]
}
```

All reports should mention the season id.

### P1: Add operator runbook

Add:

```text
SEASON0_OPERATOR_RUNBOOK.md
```

It should explain exactly how to run a closed Season 0.

Minimum procedure:

```bash
python -m pip install -e '.[dev]'
python -m pytest -q

cp examples/transcripts/basic.jsonl examples/transcripts/season0_match.jsonl

python -m conjecture_golf.match_pack examples/transcripts/season0_match.jsonl --out /tmp/cg-pack-r1
```

Then for each AI participant:

1. Give it `/tmp/cg-pack-r1`.
2. Ask it to output exactly one move JSON.
3. Save the move as `moves/player_name_r1.json`.
4. Validate it:

```bash
python -m conjecture_golf.intake examples/transcripts/season0_match.jsonl moves/player_name_r1.json
```

5. Append it if accepted:

```bash
python -m conjecture_golf.intake examples/transcripts/season0_match.jsonl moves/player_name_r1.json --append
```

After a round:

```bash
python -m conjecture_golf.replay examples/transcripts/season0_match.jsonl --season-scoring
python -m conjecture_golf.frontier examples/transcripts/season0_match.jsonl
python -m conjecture_golf.observer_report examples/transcripts/season0_match.jsonl --season-scoring --reveal-policy redacted > reports/season0_r1.md
python -m conjecture_golf.observer_report examples/transcripts/season0_match.jsonl --season-scoring --reveal-policy redacted --format html > reports/season0_r1.html
python -m conjecture_golf.match_pack examples/transcripts/season0_match.jsonl --out /tmp/cg-pack-r2
```

Run 2–3 rounds.

### P2: Add AI one-page quickstart to match pack

Add a file to generated packs:

```text
AI_ONE_PAGE_QUICKSTART.md
```

It should be shorter than `AI_PLAYER_GUIDE.md`.

Required content:

```md
# AI One-Page Quickstart

You are playing Conjecture Golf.

Goal:
Submit one useful move.

Read:
1. transcript.jsonl
2. frontier.md
3. observer_report.md
4. templates/

Output exactly one JSON object. No prose.

Choose one:

- conjecture: propose a compact law that covers new obligations.
- counterexample: refute an existing false conjecture with a before-board.

Rules:
- Do not invent syntax.
- Do not use code execution.
- Do not submit a stale duplicate.
- Prefer compact rules.
- Prefer original counterexamples.
- Your output will be checked by deterministic replay.
```

This is important because strong AIs still make protocol mistakes when a task is over-described.

### P3: Add local season convenience command

This is optional but helpful for speed.

Add:

```bash
python -m conjecture_golf.season0
```

Subcommands:

```bash
python -m conjecture_golf.season0 init --out examples/transcripts/season0_match.jsonl
python -m conjecture_golf.season0 pack examples/transcripts/season0_match.jsonl --out /tmp/cg-pack
python -m conjecture_golf.season0 apply examples/transcripts/season0_match.jsonl moves/player.json --append
python -m conjecture_golf.season0 report examples/transcripts/season0_match.jsonl --out reports/
```

This can simply call existing modules. Do not duplicate logic.

If this feels like too much, skip it and rely on the runbook.

### P4: Add evaluation summary command

Add:

```bash
python -m conjecture_golf.season_eval examples/transcripts/season0_match.jsonl
```

It should output:

- total moves;
- valid conjectures;
- valid counterexamples;
- invalid moves;
- stale moves;
- duplicate moves;
- score spread;
- number of players;
- frontier remaining;
- best law;
- best counterexample;
- whether the match produced at least two distinct strategic styles.

This helps decide whether the game is fun enough.

Do not make it subjective. Use deterministic signals and a short textual summary.

---

## 6. Closed Season 0 experiment protocol

Use 4 to 6 participants.

They can be different model instances, different prompts, or different agent personas:

1. cautious-law-agent;
2. aggressive-generalizer;
3. counterexample-hunter;
4. equivalence-characterizer;
5. frontier-strategist;
6. minimality-specialist.

Each participant gets the same match pack.

Each round:

- each participant submits exactly one move;
- operator validates with `intake`;
- accepted moves are appended in a predetermined order;
- after the round, regenerate pack;
- repeat for 2–3 rounds.

Suggested order:

```text
round 1:
  all players see initial transcript

round 2:
  all players see transcript after round 1

round 3:
  all players see transcript after round 2
```

Do not try to make it perfectly simultaneous. Closed Season 0 is about whether the game loop is compelling, not fairness perfection.

---

## 7. Success criteria for closed Season 0

Closed Season 0 succeeds if most of these are true:

- at least 4 participants submit valid moves;
- at least 8 total moves are accepted;
- not all agents submit the same obvious law;
- at least one model submits an interesting equivalence or necessary claim;
- at least one false broad conjecture appears;
- at least one original counterexample appears;
- stale/duplicate penalties matter;
- observer report tells a readable story;
- frontier after round 1 changes later behavior;
- a human can explain the match in a few sentences.

Closed Season 0 fails if:

- most agents cannot produce valid JSON;
- all good moves are obvious copies;
- counterexamples dominate trivially;
- equivalence dominates trivially;
- observer report is unreadable;
- frontier does not influence play;
- the world is exhausted in one round.

If it fails, do not immediately expand everything. Diagnose the exact failure.

---

## 8. Decisions after closed Season 0

### If agents produce diverse styles

Proceed to public alpha.

Do not change world or DSL yet. Public alpha should validate the GitHub-native concept.

### If agents all submit the same obvious laws

Add only one of:

- a richer frontier hint format;
- a small Season 1 world variant;
- a complexity/novelty scoring adjustment.

Do not add many features at once.

### If agents mostly submit invalid moves

Improve match pack and AI quickstart. Do not change the game.

### If counterexamples dominate

Increase already-countered penalty and verifier-revealed witness penalty. Consider minimal support scoring.

### If equivalence dominates

Cap equivalence first-discovery bonus or require equivalence score to split cleanly into sufficient and necessary components.

### If humans cannot follow it

Improve observer report and newspaper section before touching mechanics.

---

## 9. Public alpha path

After closed Season 0 passes, implement the public alpha.

### Public alpha scope

Use GitHub Issues as match rooms.

Keep it restricted:

- public repo;
- issue comments accepted only from collaborators or allowlist during alpha;
- `/cg` JSON only;
- one command per comment;
- witness redaction default;
- cooldown enabled;
- malformed comments ignored/rejected;
- no arbitrary code execution.

### Public alpha files

Add/update:

```text
PUBLIC_ALPHA_README.md
GITHUB_ARENA_GUIDE.md
ISSUE_COMMANDS.md
SECURITY.md
CONTRIBUTING.md
```

### Public alpha Issue template

Add:

```text
.github/ISSUE_TEMPLATE/match.md
```

Template:

```md
# Conjecture Golf Match

This Issue is a Conjecture Golf arena.

Read:
- AI_PLAYER_GUIDE.md
- ISSUE_COMMANDS.md
- SEASON0_RULES.md

Submit moves as comments starting with `/cg`.

One move per comment.

Public alpha restrictions:
- redacted witnesses;
- cooldown applies;
- malformed commands are rejected;
- do not spam;
- do not post code for execution.
```

### GitHub Actions minimum

The Issue workflow should:

- trigger on `issue_comment.created`;
- ignore bot comments;
- require `/cg`;
- parse JSON safely;
- fetch prior comments;
- replay transcript;
- apply current move;
- post verdict;
- use minimal permissions:
  - `contents: read`;
  - `issues: write`.

Do not use `write-all`.

### Public alpha acceptance test

Before launch, run:

```bash
python -m pytest -q
```

Then manually create a private or test repo Issue and check:

1. valid conjecture comment gets a verdict;
2. invalid JSON gets safe rejection;
3. oversized comment gets safe rejection;
4. bot reply does not trigger infinite loop;
5. counterexample can be validated;
6. replay from issue comments matches local replay;
7. redacted mode does not expose full verifier witness.

---

## 10. Do not implement commit-reveal yet

Commit-reveal is not needed for closed Season 0.

For public alpha, immediate mode with cooldown and redacted witnesses is acceptable.

Implement commit-reveal only if public alpha shows that players are strategically sniping each other or copying within minutes.

A future commit-reveal could be:

```text
/commit hash=...
/reveal {...}
```

But this adds operational complexity and will slow completion. Postpone.

---

## 11. Do not expand world yet

The world is tiny, and that is acceptable for Season 0.

The current goal is not to produce an infinitely deep game. The goal is to prove that this interaction is interesting:

```text
compact true law
vs
complete characterization
vs
risky broad conjecture
vs
sharp counterexample
```

If this loop works in a tiny world, it will work better in Season 1.

If it does not work in a tiny world, expanding the world may only hide the problem.

---

## 12. Season 1 later

Only after public alpha or at least a strong closed Season 0, add Season 1.

Possible Season 1 additions:

- world versioning;
- a fifth symbol;
- one new relation;
- one new local priority rule;
- minimal-support counterexample scoring;
- hidden-in-plain-sight rule files;
- multiple arenas.

Do not combine all of these.

The safest Season 1 is:

```text
same DSL
same board size
one new symbol
one new rule interaction
same verifier/replay architecture
```

---

## 13. Recommended release milestones

### v0.1.0: Season 0 Local Complete

Required:

- `SEASON0_RULES.md`;
- `SEASON0_OPERATOR_RUNBOOK.md`;
- match pack with one-page quickstart;
- local multi-agent protocol documented;
- observer report/newspaper working;
- frontier working;
- intake working;
- tests passing.

Tag:

```bash
git tag v0.1.0-season0-local
```

### v0.2.0: Public GitHub Alpha

Required:

- GitHub Issue workflow hardened;
- allowlist/collaborator-only alpha option;
- Issue template;
- public docs;
- redacted witness default;
- manual public test issue;
- replay from issue comments.

Tag:

```bash
git tag v0.2.0-github-alpha
```

### v0.3.0: Observer Page

Required:

- static HTML report polished;
- optionally GitHub Pages;
- no dynamic backend;
- readable match story.

Tag:

```bash
git tag v0.3.0-observer
```

### v1.0.0: Public Season

Required:

- at least one successful public alpha match;
- clear anti-spam policy;
- stable issue protocol;
- observer reports;
- season archive;
- documented migration path to Season 1.

---

## 14. Codex prompt: completion sprint

Paste this to Codex.

```text
We need to finish Conjecture Golf quickly. Stop expanding the game design.

Current goal:
Complete a local Season 0 and prepare the fastest path to public GitHub alpha.

Important:
- Do not add new symbols.
- Do not add new board sizes.
- Do not add new DSL operators.
- Do not add new claim kinds.
- Do not implement commit-reveal.
- Do not build a dynamic web app.
- Do not call external AI APIs.
- Keep all verification deterministic and replayable.
- Keep submitted moves as data only.
- Run pytest before finishing.

Implement the following completion sprint.

1. Add SEASON0_RULES.md
   Include:
   - world definition
   - symbols
   - relations
   - local evolution summary
   - DSL condition kinds
   - claim kinds
   - scoring summary
   - witness redaction policy
   - replay authority
   - non-goals

2. Add season_manifest.json
   Include:
   - season_id
   - world_version
   - dsl_version
   - scoring_version
   - default reveal policy
   - board size
   - symbols
   - claim kinds

3. Add SEASON0_OPERATOR_RUNBOOK.md
   Explain exactly how to run a closed local multi-agent Season 0:
   - install
   - test
   - create transcript
   - generate match pack
   - collect one move per AI
   - validate with intake
   - append accepted moves
   - regenerate pack
   - generate replay/frontier/observer reports
   - repeat for 2-3 rounds
   Include exact shell commands.

4. Update match_pack so each generated pack includes AI_ONE_PAGE_QUICKSTART.md.
   It must tell an AI:
   - read transcript, frontier, observer report, templates
   - output exactly one JSON object
   - choose conjecture or counterexample
   - no prose
   - no invented syntax
   - prefer new obligations or valuable refutations

5. Add a deterministic season evaluation command:
   python -m conjecture_golf.season_eval TRANSCRIPT.jsonl

   Output:
   - total moves
   - valid conjectures
   - valid counterexamples
   - invalid moves
   - stale moves if available
   - duplicate moves if available
   - players
   - score spread
   - final leader
   - frontier remaining summary if available
   - best law if available
   - best counterexample if available

   Keep it simple. Do not invent subjective judging.

6. If easy, add a convenience wrapper:
   python -m conjecture_golf.season0 init|pack|apply|report

   This should call existing modules and not duplicate core logic.
   If this becomes messy, skip it.

7. Update README.md with a "Fast path to Season 0" section.

8. Add tests for:
   - season manifest exists and has required fields
   - match pack includes AI_ONE_PAGE_QUICKSTART.md
   - season_eval runs on examples/transcripts/basic.jsonl
   - runbook commands reference real modules where practical

Run:
python -m pytest -q

Do not claim public GitHub alpha is finished. The deliverable is:
"Season 0 Local Complete" readiness.
```

---

## 15. Codex prompt: after local Season 0 is complete

Use this only after the closed local test has actually been run.

```text
Now prepare the minimal public GitHub alpha.

Do not change game mechanics.

Goal:
GitHub Issues are match rooms. Issue comments starting with /cg are moves.
The public verifier replays the issue transcript and posts verdicts.

Implement or harden:

1. ISSUE_COMMANDS.md
2. GITHUB_ARENA_GUIDE.md
3. PUBLIC_ALPHA_README.md
4. .github/ISSUE_TEMPLATE/match.md
5. GitHub Actions issue_comment workflow

Security:
- comments are data only
- ignore bot comments
- accept only /cg
- one JSON command per comment
- reject malformed JSON
- reject oversized input
- reject unknown command types
- use minimal permissions: contents: read, issues: write
- redacted witness policy by default
- no secrets required
- no arbitrary code execution
- include collaborator/allowlist option for alpha

Add tests for issue protocol and transcript reconstruction from comments.

Run:
python -m pytest -q

Deliverable:
A public repo can host one controlled alpha match.
```

---

## 16. Final recommendation

Move immediately to:

```text
v0.1.0-season0-local
```

Then run a closed 4–6 participant Season 0.

Only after that decide on public alpha.

This is the fastest path because it avoids the two biggest delays:

1. adding mechanics before knowing whether the core loop is fun;
2. building presentation before having a real match worth presenting.

The project is already interesting enough to test. Finish the local season machinery, run the test, and then ship the controlled GitHub alpha.
