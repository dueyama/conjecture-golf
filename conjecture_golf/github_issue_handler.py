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

from .arena_packet import build_arena_turn_packet, render_arena_turn_packet_markdown
from .arena_branch_store import write_branch_store
from .arena_gate import DEFAULT_CANONICAL_BRANCH, DEFAULT_INVALID_STRIKES_TO_DISQUALIFY, DEFAULT_QUARANTINE_BRANCH
from .arena_issue import (
    command_from_issue_comment,
    render_routing_markdown,
    route_issue_comments,
    write_routing_artifacts,
)
from .issue_protocol import (
    attach_issue_metadata,
    commands_from_issue_comments,
    parse_issue_comment,
    render_state_markdown,
    render_verdict_markdown,
)
from .replay import apply_command, replay_records
from .season_catalog import load_optional_compiled_season

DEFAULT_MIN_PLAYER_INTERVAL_SECONDS = 6 * 60 * 60
DEFAULT_SEASON_ARCHIVE_URL = (
    "https://github.com/dueyama/conjecture-golf/blob/main/seasons/season_2_summary.md"
)


def _env_bool(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def run_gh(args: list[str]) -> str:
    completed = subprocess.run(["gh", *args], check=True, text=True, capture_output=True)
    return completed.stdout


def _git_head_commit() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return completed.stdout.strip()


def _write_verdict(markdown: str) -> None:
    out_path = os.environ.get("VERDICT_FILE", "verdict.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(markdown)


def _status_markdown(status: str, *, season_archive_url: str, message: str = "") -> str:
    if status == "closed":
        detail = message or "Conjecture Golf is closed. No further moves are accepted."
        return (
            "**Conjecture Golf season closed**\n\n"
            f"{detail}\n\n"
            f"Season archive: {season_archive_url}\n"
        )
    detail = message or "This Issue is not the active Conjecture Golf arena."
    return (
        "**Conjecture Golf arena moved**\n\n"
        f"{detail}\n\n"
        f"Season archive: {season_archive_url}\n"
    )


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


def _current_comment() -> dict[str, Any]:
    comment: dict[str, Any] = {
        "body": os.environ.get("COMMENT_BODY", ""),
        "user": {"login": os.environ.get("COMMENT_AUTHOR", "")},
    }
    comment_created_at = os.environ.get("COMMENT_CREATED_AT", "")
    comment_id = os.environ.get("COMMENT_ID", "")
    if comment_created_at:
        comment["created_at"] = comment_created_at
    if comment_id:
        comment["id"] = comment_id
    return comment


def _prior_comments(comments: list[dict[str, Any]], current: dict[str, Any]) -> list[dict[str, Any]]:
    comment_body = current.get("body", "")
    comment_id = current.get("id")
    prior_comments = []
    for comment in comments:
        body = comment.get("body", "")
        # Exclude the current command from prior replay.
        if comment_id and str(comment.get("id")) == str(comment_id):
            break
        if (
            not comment_id
            and isinstance(body, str)
            and isinstance(comment_body, str)
            and body.strip() == comment_body.strip()
        ):
            break
        prior_comments.append(comment)
    return prior_comments


def main() -> int:
    comment_body = os.environ.get("COMMENT_BODY", "")
    issue_number = os.environ.get("ISSUE_NUMBER", "")
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY", "")
    author_login = os.environ.get("COMMENT_AUTHOR", "")
    arena_status = os.environ.get("CG_ARENA_STATUS", "closed").strip().lower()
    arena_status_message = os.environ.get("CG_ARENA_STATUS_MESSAGE", "").strip()
    season_archive_url = os.environ.get(
        "CG_SEASON_ARCHIVE_URL", DEFAULT_SEASON_ARCHIVE_URL
    ).strip()

    if not issue_number or not repo:
        print("Missing ISSUE_NUMBER or GH_REPO/GITHUB_REPOSITORY", file=sys.stderr)
        return 2

    try:
        # Only an explicit, recognized active status may enter the write path.
        # Missing and unknown statuses fail closed.
        if arena_status != "active":
            current_comment = _current_comment()
            if command_from_issue_comment(current_comment) is None:
                print("Not a Conjecture Golf command; nothing to do.")
                return 0
            markdown = _status_markdown(
                "redirect" if arena_status == "redirect" else "closed",
                season_archive_url=season_archive_url,
                message=arena_status_message,
            )
            _write_verdict(markdown)
            print(markdown)
            return 0

        min_player_interval_seconds = int(
            os.environ.get(
                "CG_MIN_PLAYER_INTERVAL_SECONDS", str(DEFAULT_MIN_PLAYER_INTERVAL_SECONDS)
            )
        )
        season_scoring = _env_bool("CG_SEASON_SCORING", default=True)
        reveal_policy = os.environ.get(
            "CG_REVEAL_POLICY", "redacted" if season_scoring else "full"
        )
        arena_gate = _env_bool("CG_ARENA_GATE", default=True)
        canonical_branch = os.environ.get("CG_CANONICAL_BRANCH", DEFAULT_CANONICAL_BRANCH)
        quarantine_branch = os.environ.get("CG_QUARANTINE_BRANCH", DEFAULT_QUARANTINE_BRANCH)
        season_spec_path = os.environ.get("CG_SEASON_SPEC", "").strip() or None
        season = load_optional_compiled_season(season_spec_path)
        invalid_strikes_to_disqualify = int(
            os.environ.get(
                "CG_INVALID_STRIKES_TO_DISQUALIFY",
                str(DEFAULT_INVALID_STRIKES_TO_DISQUALIFY),
            )
        )
        rules_ref = os.environ.get("CG_RULES_REF", "").strip()
        rules_commit = os.environ.get("CG_RULES_COMMIT", "").strip() or _git_head_commit()

        if arena_gate:
            current_comment = _current_comment()
            if command_from_issue_comment(current_comment) is None:
                print("Not a Conjecture Golf command; nothing to do.")
                return 0
            comments = fetch_issue_comments(repo, issue_number)
            routing = route_issue_comments(
                [*_prior_comments(comments, current_comment), current_comment],
                min_player_interval_seconds=min_player_interval_seconds,
                season_scoring=season_scoring,
                season=season,
                invalid_strikes_to_disqualify=invalid_strikes_to_disqualify,
                canonical_branch=canonical_branch,
                quarantine_branch=quarantine_branch,
            )
            decision = routing.current_decision
            if decision is None:
                print("Not a Conjecture Golf command; nothing to do.")
                return 0
            state = replay_records(
                routing.canonical_records,
                min_player_interval_seconds=min_player_interval_seconds,
                season_scoring=season_scoring,
                season=season,
            )
            arena_packet = build_arena_turn_packet(
                canonical_records=routing.canonical_records,
                quarantine_records=routing.quarantine_records,
                decision=decision,
                canonical_branch=canonical_branch,
                quarantine_branch=quarantine_branch,
                invalid_strikes_to_disqualify=invalid_strikes_to_disqualify,
                min_player_interval_seconds=min_player_interval_seconds,
                season_scoring=season_scoring,
                season=season,
                rules_ref=rules_ref,
                rules_commit=rules_commit,
            )
            markdown = (
                render_routing_markdown(decision, reveal_policy=reveal_policy)
                + "\n\n"
                + render_state_markdown(state)
                + "\n\n"
                + render_arena_turn_packet_markdown(arena_packet)
            )
            write_routing_artifacts(
                routing,
                canonical_path=os.environ.get("CG_CANONICAL_TRANSCRIPT_FILE"),
                quarantine_path=os.environ.get("CG_QUARANTINE_TRANSCRIPT_FILE"),
                decision_path=os.environ.get("CG_ARENA_DECISION_FILE"),
            )
            branch_store_dir = os.environ.get("CG_BRANCH_STORE_DIR")
            if branch_store_dir:
                write_branch_store(
                    canonical_records=routing.canonical_records,
                    quarantine_records=routing.quarantine_records,
                    decisions=[decision.to_dict() for decision in routing.decisions],
                    out_dir=branch_store_dir,
                    canonical_branch=canonical_branch,
                    quarantine_branch=quarantine_branch,
                    invalid_strikes_to_disqualify=invalid_strikes_to_disqualify,
                )
            _write_verdict(markdown)
            print(markdown)
            return 0

        parse_result = parse_issue_comment(comment_body, author_login=author_login)
        if not parse_result.accepted or not parse_result.parsed:
            print("Not a Conjecture Golf command; nothing to do.")
            return 0

        comments = fetch_issue_comments(repo, issue_number)
        current_comment = _current_comment()
        prior_comments = _prior_comments(comments, current_comment)

        prior_commands = commands_from_issue_comments(prior_comments)
        current_command = attach_issue_metadata(parse_result.parsed.command, current_comment)
        state = replay_records(
            prior_commands,
            min_player_interval_seconds=min_player_interval_seconds,
            season_scoring=season_scoring,
            season=season,
        )
        verdict = apply_command(
            state,
            current_command,
            min_player_interval_seconds=min_player_interval_seconds,
            season_scoring=season_scoring,
            season=season,
        )
        markdown = render_verdict_markdown(verdict, reveal_policy=reveal_policy) + "\n\n" + render_state_markdown(state)
        _write_verdict(markdown)
        print(markdown)
        return 0
    except Exception as exc:  # noqa: BLE001 - this is a public issue handler; fail closed.
        markdown = f"❌ **Conjecture Golf command rejected**\n\n```text\n{exc}\n```"
        _write_verdict(markdown)
        print(markdown)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
