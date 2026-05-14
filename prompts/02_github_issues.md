# Prompt 02: Harden GitHub Issue play

Read AGENTS.md first.

Task:
Improve GitHub Issue support so Issues can become match rooms.

Constraints:
- Comments are data only.
- Accept only comments starting with /cg.
- Parse exactly one JSON object after /cg.
- Reject oversized comments.
- Ignore bot comments.
- Use minimal GitHub token permissions.
- Do not run untrusted code.

Implement or improve:
1. tests for github_issue_handler behavior using mocked gh output.
2. transcript reconstruction from prior Issue comments.
3. duplicate-command handling.
4. better Markdown verdict comments.
5. failure-closed behavior for malformed commands.

Done when:
- pytest passes.
- The workflow can be reviewed without requiring secrets.
- The local replay remains the final authority.
