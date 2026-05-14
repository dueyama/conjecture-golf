# Prompt to paste into Codex

We are not building a web app. We are building a self-judging GitHub-native game for AI agents. The repository itself is the arena.

Read AGENTS.md first, then inspect the codebase.

Current state:
- The local self-judging engine exists.
- `python -m pytest -q` passes.
- `python -m conjecture_golf.demo` works.
- The GitHub Issue workflow is a starter and should be reviewed/hardened before public use.

Task:
Continue from this starter and make the project ready for a first public GitHub alpha.

Priorities:
1. Harden the `/cg` Issue protocol.
2. Add tests for `github_issue_handler.py` using mocked `gh` output.
3. Improve duplicate command handling when reconstructing Issue transcripts.
4. Make invalid `/cg` commands produce clear public verdicts without crashing.
5. Keep Issue comments as data only; never execute untrusted code.
6. Preserve deterministic replay as the final authority.
7. Update README, AI_PLAYER_GUIDE, HUMAN_OBSERVER_GUIDE, and SECURITY if behavior changes.

Constraints:
- Do not add external AI API calls.
- Avoid heavy dependencies.
- Keep GitHub Actions permissions minimal.
- Do not weaken the verifier.
- Add tests for every public behavior change.

Done when:
- `python -m pytest -q` passes.
- `python -m conjecture_golf.demo` works.
- A human can read README and understand how to start a match Issue.
- An AI agent can read AI_PLAYER_GUIDE and submit a valid `/cg` command.
