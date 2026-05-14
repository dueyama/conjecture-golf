# Prompt 03: Add an observer page generator

Read AGENTS.md first.

Task:
Create a static observer page generator for human readers.

Goal:
Given transcript files, generate a small static HTML page showing:
- match summary
- move list
- current leaderboard
- selected boards before/after
- explanation of conjectures and counterexamples

Constraints:
- No heavy web framework.
- Static output only.
- Deterministic from transcripts.
- No external network calls.

Suggested command:
python -m conjecture_golf.render_site examples/transcripts/*.jsonl --out site/

Done when:
- pytest passes.
- Generated output is deterministic.
- README explains how to render it.
