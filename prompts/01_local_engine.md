# Prompt 01: Continue the local self-judging engine

Use this repository as a starter for Conjecture Golf.

Read AGENTS.md first.

Task:
Improve the local self-judging engine without changing the core idea.

Goals:
- Make the verifier clearer and more robust.
- Keep all results deterministic and replayable.
- Add tests for any behavior you change.
- Do not add external AI API calls.
- Do not execute untrusted code.

Suggested improvements:
1. Add more readable verdict explanations.
2. Add stricter schema validation for commands.
3. Add more examples of true and false conjectures.
4. Add tests for edge cells and priority-order effects.
5. Make replay error handling more explicit.

Done when:
- python -m pytest -q passes.
- python -m conjecture_golf.demo works.
- README and AI_PLAYER_GUIDE remain accurate.
