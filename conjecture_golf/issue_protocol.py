"""GitHub Issue command protocol for Conjecture Golf.

Issue comments are data, not code. Only comments that begin with `/cg` are
considered game commands.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from .replay import ReplayState, apply_command, replay_records
from .score import leaderboard_rows, render_markdown
from .verify import Verdict, redact_verdict
from .world import ValidationError

COMMAND_PREFIX = "/cg"
MAX_COMMENT_CHARS = 8000
BOT_LOGINS = {"github-actions[bot]", "dependabot[bot]"}
ALLOWED_COMMAND_TYPES = {"hello", "conjecture", "counterexample", "score"}


@dataclass(frozen=True)
class ParsedIssueCommand:
    command: dict[str, Any]
    raw_json: str


@dataclass(frozen=True)
class IssueParseResult:
    accepted: bool
    parsed: ParsedIssueCommand | None = None
    reason: str | None = None


def parse_issue_comment(text: str, *, author_login: str | None = None) -> IssueParseResult:
    """Parse a GitHub Issue comment into a game command.

    Returns accepted=False for comments that are not commands. This lets normal
    human discussion happen in the same Issue without triggering the game.
    """

    if author_login in BOT_LOGINS:
        return IssueParseResult(False, reason="ignored bot comment")
    if not isinstance(text, str):
        return IssueParseResult(False, reason="comment body is not text")
    stripped = text.strip()
    if not stripped.startswith(COMMAND_PREFIX):
        return IssueParseResult(False, reason="not a /cg command")
    if len(stripped) > MAX_COMMENT_CHARS:
        raise ValidationError(f"comment is too long; max is {MAX_COMMENT_CHARS} chars")

    raw = stripped[len(COMMAND_PREFIX) :].strip()
    if not raw:
        raise ValidationError("/cg command must be followed by a JSON object")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON after /cg: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("/cg payload must be a JSON object")
    if "_meta" in payload:
        raise ValidationError("_meta is reserved for public transcript metadata")
    command_type = payload.get("type")
    if command_type not in ALLOWED_COMMAND_TYPES:
        raise ValidationError(f"command type must be one of {sorted(ALLOWED_COMMAND_TYPES)}")
    return IssueParseResult(True, parsed=ParsedIssueCommand(command=payload, raw_json=raw))


def attach_issue_metadata(command: Mapping[str, Any], comment: Mapping[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {"source": "github_issue"}
    user = comment.get("user") or {}
    if isinstance(user, Mapping) and isinstance(user.get("login"), str):
        meta["author_login"] = user["login"]
    if "created_at" in comment:
        meta["created_at"] = comment["created_at"]
    if "id" in comment:
        meta["comment_id"] = comment["id"]
    return {**dict(command), "_meta": meta}


def commands_from_issue_comments(comments: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Extract valid /cg commands from GitHub Issue comment objects.

    Malformed /cg comments are included as invalid commands so replay can give a
    penalty and a public explanation. Non-/cg comments are ignored.
    """

    commands: list[dict[str, Any]] = []
    for comment in comments:
        body = comment.get("body", "")
        user = comment.get("user") or {}
        author_login = user.get("login") if isinstance(user, Mapping) else None
        try:
            result = parse_issue_comment(body, author_login=author_login)
            if result.accepted and result.parsed:
                commands.append(attach_issue_metadata(result.parsed.command, comment))
        except ValidationError as exc:
            invalid_player = author_login or "invalid-comment"
            commands.append(
                attach_issue_metadata(
                    {
                        "type": "invalid",
                        "player": invalid_player,
                        "message": str(exc),
                        "reason": "malformed_issue_comment",
                    },
                    comment,
                )
            )
    return commands


def render_verdict_markdown(verdict: Verdict, *, reveal_policy: str = "full") -> str:
    verdict = redact_verdict(verdict, reveal_policy=reveal_policy)
    status = "✅" if verdict.ok else "❌"
    lines = [f"{status} **Conjecture Golf verdict**", "", f"{verdict.message}", ""]
    lines.append(f"Player: `{verdict.player}`")
    lines.append(f"Score delta: `{verdict.score_delta}`")
    if verdict.details:
        detail_text = json.dumps(verdict.details, ensure_ascii=False, indent=2)
        if len(detail_text) > 3000:
            detail_text = detail_text[:3000] + "\n... truncated ..."
        lines.extend(["", "Details:", "", "```json", detail_text, "```"])
    return "\n".join(lines)


def render_state_markdown(state: ReplayState) -> str:
    rows = leaderboard_rows(state.scores)
    lines = ["## Current leaderboard", "", render_markdown(rows)]
    if state.agent_profiles:
        lines.extend(["", "## Registered agents", ""])
        for player in sorted(state.agent_profiles):
            profile = state.agent_profiles[player]
            kind = profile.get("kind", "unknown")
            model = profile.get("model_name") or profile.get("model_family") or "unspecified model"
            autonomy = profile.get("autonomy", "unspecified autonomy")
            lines.append(f"- `{player}`: `{kind}`, `{model}`, `{autonomy}`")
    return "\n".join(lines)


def handle_issue_command(
    command: Mapping[str, Any],
    prior_commands: list[Mapping[str, Any]] | None = None,
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
) -> tuple[Verdict, ReplayState]:
    state = replay_records(
        prior_commands or [],
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
    )
    verdict = apply_command(
        state,
        command,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
    )
    return verdict, state
