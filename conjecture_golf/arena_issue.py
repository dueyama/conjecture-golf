"""Deterministic arena routing for GitHub Issue comments.

This module folds public Issue comments into two replayable data streams:
canonical game commands and quarantine records. It treats every comment as
data, never as code, and uses the same arena gate that local operators can run.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .arena_gate import DEFAULT_INVALID_STRIKES_TO_DISQUALIFY, GateDecision, gate_move
from .issue_protocol import attach_issue_metadata, parse_issue_comment, render_verdict_markdown
from .season_catalog import load_optional_compiled_season
from .season_engine import CompiledSeason
from .verify import Verdict
from .world import ValidationError


@dataclass(frozen=True)
class ArenaIssueRouting:
    canonical_records: list[dict[str, Any]]
    quarantine_records: list[dict[str, Any]]
    decisions: list[GateDecision]

    @property
    def current_decision(self) -> GateDecision | None:
        return self.decisions[-1] if self.decisions else None


def command_from_issue_comment(comment: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return a normalized command for one Issue comment, or None if ignored."""

    body = comment.get("body", "")
    user = comment.get("user") or {}
    author_login = user.get("login") if isinstance(user, Mapping) else None
    try:
        result = parse_issue_comment(body, author_login=author_login)
    except ValidationError as exc:
        invalid_player = author_login or "invalid-comment"
        return attach_issue_metadata(
            {
                "type": "invalid",
                "player": invalid_player,
                "message": str(exc),
                "reason": "malformed_issue_comment",
            },
            comment,
        )

    if not result.accepted or not result.parsed:
        return None
    return attach_issue_metadata(result.parsed.command, comment)


def route_issue_comments(
    comments: Sequence[Mapping[str, Any]],
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
    season: CompiledSeason | None = None,
    invalid_strikes_to_disqualify: int = DEFAULT_INVALID_STRIKES_TO_DISQUALIFY,
    canonical_branch: str = "arena/season-0",
    quarantine_branch: str = "quarantine/season-0",
) -> ArenaIssueRouting:
    """Fold Issue comments into canonical and quarantine records."""

    canonical_records: list[dict[str, Any]] = []
    quarantine_records: list[dict[str, Any]] = []
    decisions: list[GateDecision] = []
    for comment in comments:
        command = command_from_issue_comment(comment)
        if command is None:
            continue
        decision = gate_move(
            canonical_records,
            quarantine_records,
            command,
            min_player_interval_seconds=min_player_interval_seconds,
            season_scoring=season_scoring,
            season=season,
            invalid_strikes_to_disqualify=invalid_strikes_to_disqualify,
            canonical_branch=canonical_branch,
            quarantine_branch=quarantine_branch,
        )
        decisions.append(decision)
        if decision.accepted and decision.canonical_command is not None:
            canonical_records.append(decision.canonical_command)
        elif decision.quarantine_record is not None:
            quarantine_records.append(decision.quarantine_record)
    return ArenaIssueRouting(
        canonical_records=canonical_records,
        quarantine_records=quarantine_records,
        decisions=decisions,
    )


def render_routing_markdown(decision: GateDecision, *, reveal_policy: str = "full") -> str:
    verdict = Verdict(**decision.verdict)
    lines = [render_verdict_markdown(verdict, reveal_policy=reveal_policy), "", "## Arena routing", ""]
    if decision.accepted:
        lines.append(f"Accepted for canonical branch: `{decision.branch}`")
    else:
        lines.append(f"Routed to quarantine branch: `{decision.branch}`")
    lines.append(f"Reason: `{decision.reason}`")
    lines.append(f"Invalid strikes: `{decision.strikes_before}` -> `{decision.strikes_after}`")
    return "\n".join(lines)


def write_jsonl(path: str | Path, records: Sequence[Mapping[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            f.write("\n")


def write_routing_artifacts(
    routing: ArenaIssueRouting,
    *,
    canonical_path: str | Path | None = None,
    quarantine_path: str | Path | None = None,
    decision_path: str | Path | None = None,
) -> None:
    if canonical_path:
        write_jsonl(canonical_path, routing.canonical_records)
    if quarantine_path:
        write_jsonl(quarantine_path, routing.quarantine_records)
    if decision_path:
        Path(decision_path).parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "canonical_records": len(routing.canonical_records),
            "quarantine_records": len(routing.quarantine_records),
            "decisions": [decision.to_dict() for decision in routing.decisions],
        }
        Path(decision_path).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def load_issue_comments(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        comments: list[dict[str, Any]] = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid Issue comment JSON on line {line_no}: {exc.msg}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"Issue comment line {line_no} must be a JSON object")
            comments.append(record)
        return comments

    if isinstance(payload, dict) and isinstance(payload.get("comments"), list):
        payload = payload["comments"]
    if not isinstance(payload, list):
        raise ValueError("Issue comments input must be a JSON array, JSONL stream, or object with a comments array")
    comments = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            raise ValueError(f"Issue comment at index {index} must be a JSON object")
        comments.append(item)
    return comments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstruct arena streams from public GitHub Issue comments.")
    parser.add_argument("comments", help="GitHub Issue comments JSON array or JSONL path")
    parser.add_argument("--canonical", help="Write canonical transcript JSONL here")
    parser.add_argument("--quarantine", help="Write quarantine JSONL here")
    parser.add_argument("--decision", help="Write routing decision JSON here")
    parser.add_argument("--min-player-interval-seconds", type=int, default=0)
    parser.add_argument("--no-season-scoring", action="store_true")
    parser.add_argument("--season", help="Optional data-only season spec path")
    parser.add_argument("--invalid-strikes-to-disqualify", type=int, default=DEFAULT_INVALID_STRIKES_TO_DISQUALIFY)
    parser.add_argument("--canonical-branch", default="arena/season-0")
    parser.add_argument("--quarantine-branch", default="quarantine/season-0")
    args = parser.parse_args(argv)

    season = load_optional_compiled_season(args.season)
    routing = route_issue_comments(
        load_issue_comments(args.comments),
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=not args.no_season_scoring,
        season=season,
        invalid_strikes_to_disqualify=args.invalid_strikes_to_disqualify,
        canonical_branch=args.canonical_branch,
        quarantine_branch=args.quarantine_branch,
    )
    write_routing_artifacts(
        routing,
        canonical_path=args.canonical,
        quarantine_path=args.quarantine,
        decision_path=args.decision,
    )
    summary = {
        "accepted": sum(1 for decision in routing.decisions if decision.accepted),
        "canonical_records": len(routing.canonical_records),
        "decisions": len(routing.decisions),
        "quarantine_records": len(routing.quarantine_records),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
