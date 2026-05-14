"""GitHub Actions entrypoint for handling Conjecture Golf issue comments.

This module intentionally uses the GitHub CLI (`gh`) instead of direct HTTP
libraries to avoid extra dependencies. It is safe for a first MVP, but public
repositories should still review token permissions carefully.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

from .issue_protocol import parse_issue_comment, render_state_markdown, render_verdict_markdown
from .replay import apply_command, replay_records
from .world import ValidationError


def run_gh(args: list[str]) -> str:
    completed = subprocess.run(["gh", *args], check=True, text=True, capture_output=True)
    return completed.stdout


def fetch_issue_comments(repo: str, issue_number: str) -> list[dict[str, Any]]:
    output = run_gh([
        "api",
        f"repos/{repo}/issues/{issue_number}/comments",
        "--paginate",
    ])
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        # With --paginate gh may concatenate arrays in older setups. Keep the MVP simple.
        payload = []
        for line in output.splitlines():
            if line.strip():
                maybe = json.loads(line)
                if isinstance(maybe, list):
                    payload.extend(maybe)
    if not isinstance(payload, list):
        raise RuntimeError("GitHub comments API did not return a list")
    return payload


def main() -> int:
    comment_body = os.environ.get("COMMENT_BODY", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
    author_login = os.environ.get("COMMENT_AUTHOR", "")

    if not issue_number or not repo:
        print("Missing ISSUE_NUMBER or GH_REPO/GITHUB_REPOSITORY", file=sys.stderr)
        return 2

    try:
        parse_result = parse_issue_comment(comment_body, author_login=author_login)
        if not parse_result.accepted or not parse_result.parsed:
            print("Not a Conjecture Golf command; nothing to do.")
            return 0

        comments = fetch_issue_comments(repo, issue_number)
        prior_commands = []
        for comment in comments:
            body = comment.get("body", "")
            user = comment.get("user") or {}
            login = user.get("login") if isinstance(user, dict) else None
            try:
                result = parse_issue_comment(body, author_login=login)
            except ValidationError:
                continue
            if result.accepted and result.parsed:
                # Exclude the current command from prior replay by comparing raw body.
                if body.strip() == comment_body.strip():
                    break
                prior_commands.append(result.parsed.command)

        state = replay_records(prior_commands)
        verdict = apply_command(state, parse_result.parsed.command)
        markdown = render_verdict_markdown(verdict) + "\n\n" + render_state_markdown(state)
        out_path = os.environ.get("VERDICT_FILE", "verdict.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(markdown)
        return 0
    except Exception as exc:  # noqa: BLE001 - this is a public issue handler; fail closed.
        markdown = f"❌ **Conjecture Golf command rejected**\n\n```text\n{exc}\n```"
        out_path = os.environ.get("VERDICT_FILE", "verdict.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(markdown)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
