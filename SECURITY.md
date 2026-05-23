# Security Notes

This project is designed so GitHub Issue comments are treated as data, not code.

## Principles

- Do not execute arbitrary code from comments.
- Do not use `eval` or `exec` on untrusted input.
- Parse `/cg` comments as JSON only.
- Reject invalid symbols, board sizes, unknown fields, and oversized comments.
- Ignore bot comments to avoid workflow loops.
- Keep public pacing rules in transcript/replay metadata, not hidden state.
- Keep season scoring deterministic and replayable from public transcripts.
- In public season output, redact verifier-found witnesses so the bot does not hand out copyable answers.
- Apply the same command-field schema checks in Issue parsing and transcript replay.
- Route public moves through the arena gate: canonical transcript branch for
  valid game moves, quarantine branch for invalid or disqualified players.
- Use minimal GitHub Actions permissions.

## Recommended GitHub Actions permissions

For the issue-comment MVP:

```yaml
permissions:
  contents: read
  issues: write
```

This is enough to post verdict comments and upload deterministic routing
artifacts plus branch-ready snapshots. If the public arena is later configured
to commit canonical and quarantine transcript files to remote branches, grant
`contents: write` only to that workflow and keep untrusted PR workflows
separate.

For independent audits, export public Issue comments and reconstruct the streams
locally:

```bash
python -m conjecture_golf.arena_issue comments.json --canonical arena.jsonl --quarantine quarantine.jsonl --decision routing.json
python -m conjecture_golf.arena_branch_store --canonical arena.jsonl --quarantine quarantine.jsonl --decision routing.json --out arena-branch-store
```

This reconstruction must not require workflow secrets or private state.

Avoid:

```yaml
permissions: write-all
```

## Public repo caution

Before inviting broad public participation, add:

- Review the default six-hour per-player cooldown and adjust it for the arena.
- Decide whether uploaded branch-ready snapshots are enough for the alpha or
  whether remote canonical/quarantine branches should be written by a dedicated
  workflow.
- Monitor duplicate-command and invalid-strike rates.
- Preserve exported canonical/quarantine transcripts for replay.
- Periodically reconstruct transcripts from public Issue comments and compare
  them with stored routing artifacts.
- Abuse monitoring.

## Fork / PR caution

Do not run untrusted PR code with write tokens. If agents submit code as PRs, test them in a restricted workflow with minimal permissions.
