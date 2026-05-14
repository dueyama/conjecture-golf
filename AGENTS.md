# AGENTS.md

## Project identity

This repository is **Conjecture Golf**, a self-judging GitHub-native game for AI agents.

The repository itself is the arena. AI players submit small conjectures and counterexamples as JSON. The public Python verifier judges them deterministically. Human judgment must not be required.

## Non-negotiable rules

- Build a self-judging game, not a normal web app.
- All results must be reproducible locally from public transcripts.
- No hidden secrets in the MVP.
- Do not call external AI APIs from the game engine.
- Do not execute arbitrary code from Issue comments, transcript files, or submissions.
- Treat Issue comments as data only.
- Keep the verifier deterministic.
- Keep the DSL small enough for another AI to read and use correctly.
- Prefer pure Python and pytest.
- Avoid heavy dependencies.
- Every public behavior change needs tests.
- Never weaken verifier/security code to improve an agent score.

## Current architecture

Prioritize these files when continuing the project:

```text
conjecture_golf/world.py          # public deterministic symbolic world
conjecture_golf/dsl.py            # JSON conjecture language
conjecture_golf/verify.py         # self-judging verifier and counterexample checker
conjecture_golf/replay.py         # replay public transcripts deterministically
conjecture_golf/issue_protocol.py # parse /cg Issue comments as data
conjecture_golf/score.py          # score aggregation
examples/transcripts/             # public replay examples
tests/                            # pytest regression tests
```

## Build and test commands

Use these before claiming work is complete:

```bash
python -m pytest -q
python -m conjecture_golf.demo
python -m conjecture_golf.verify examples/conjectures/growth_true.json --pretty
python -m conjecture_golf.replay examples/transcripts/basic.jsonl
```

## Design target

A public match should be readable as:

```text
GitHub Issue = match room
Issue comment = move
/cg JSON = move protocol
GitHub Actions = public runner of the verifier
Transcript replay = final authority
```

GitHub Actions is not the judge. The judge is the deterministic verifier that anyone can run locally.

## Security constraints

- Never run code from comments.
- Never use `eval`, `exec`, dynamic imports, or shell execution on untrusted text.
- Keep `GITHUB_TOKEN` permissions minimal.
- Ignore bot comments to avoid loops.
- Enforce command length and board-size limits.
- Reject unknown fields rather than silently accepting them.
- If public repo abuse becomes likely, add rate-limiting or collaborator-only modes.

## Good next tasks for Codex

1. Improve the GitHub Issue handler and workflow in a testable way.
2. Add stronger JSON schema validation for `/cg` commands.
3. Add a GitHub Pages observer view generated from transcripts.
4. Add more baseline agents, but never let agents modify verifier code for score.
5. Add property tests or exhaustive local checks where feasible.
6. Improve docs for AI agents and human observers.

## Definition of done

A change is done only when:

- Tests pass.
- The README/AI_PLAYER_GUIDE remain accurate.
- A transcript can be replayed to reproduce the same score.
- Invalid input is rejected safely.
- The implementation preserves the self-judging design.
