# Security Notes

This project is designed so GitHub Issue comments are treated as data, not code.

## Principles

- Do not execute arbitrary code from comments.
- Do not use `eval` or `exec` on untrusted input.
- Parse `/cg` comments as JSON only.
- Reject invalid symbols, board sizes, unknown fields, and oversized comments.
- Ignore bot comments to avoid workflow loops.
- Use minimal GitHub Actions permissions.

## Recommended GitHub Actions permissions

For the issue-comment MVP:

```yaml
permissions:
  contents: read
  issues: write
```

Avoid:

```yaml
permissions: write-all
```

## Public repo caution

Before inviting broad public participation, add:

- Rate limiting.
- Collaborator-only alpha mode, or a player allowlist.
- Stronger JSON schema checks.
- Duplicate-command detection.
- Better transcript export.
- Abuse monitoring.

## Fork / PR caution

Do not run untrusted PR code with write tokens. If agents submit code as PRs, test them in a restricted workflow with minimal permissions.
