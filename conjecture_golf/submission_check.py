"""Participant-facing submission check for one Conjecture Golf move."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .arena_gate import (
    DEFAULT_CANONICAL_BRANCH,
    DEFAULT_INVALID_STRIKES_TO_DISQUALIFY,
    DEFAULT_QUARANTINE_BRANCH,
    gate_move,
    iter_quarantine_jsonl,
)
from .dsl import player_name_from_submission
from .intake import load_move
from .replay import iter_jsonl
from .season_catalog import load_optional_compiled_season
from .season_engine import CompiledSeason
from .verify import redact_verdict
from .world import ValidationError


def _command_player(command: Mapping[str, Any]) -> str:
    if command.get("type") == "conjecture" and isinstance(command.get("conjecture"), Mapping):
        nested = dict(command["conjecture"])
        if "player" not in nested and "player" in command:
            nested["player"] = command["player"]
        return player_name_from_submission(nested)
    return player_name_from_submission(command)


def _invalid_report(message: str, *, expected_player: str | None = None) -> dict[str, Any]:
    return {
        "accepted": False,
        "expected_player": expected_player,
        "ok": False,
        "player": None,
        "route": None,
        "status": "invalid_json",
        "verdict": {
            "ok": False,
            "kind": "invalid",
            "player": expected_player,
            "message": message,
            "score_delta": -5,
            "details": {"reason": "invalid_submission_json"},
        },
        "warnings": [],
    }


def check_submission(
    transcript_path: str | Path,
    move: Mapping[str, Any],
    *,
    expected_player: str | None = None,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
    season: CompiledSeason | None = None,
    reveal_policy: str = "redacted",
    quarantine_records: list[dict[str, Any]] | None = None,
    invalid_strikes_to_disqualify: int = DEFAULT_INVALID_STRIKES_TO_DISQUALIFY,
    canonical_branch: str = DEFAULT_CANONICAL_BRANCH,
    quarantine_branch: str = DEFAULT_QUARANTINE_BRANCH,
) -> dict[str, Any]:
    """Return a deterministic report for one candidate move.

    The check never appends and never executes submitted code. When quarantine
    records are supplied, the same arena gate used by public Issues is applied.
    """

    records = list(iter_jsonl(transcript_path)) if Path(transcript_path).exists() else []
    command = dict(move)
    player = _command_player(command)
    warnings: list[str] = []
    if command.get("type") == "score":
        warnings.append("score is legal, but it usually does not advance the frontier.")
    if command.get("type") == "hello":
        warnings.append("hello is useful once per participant; later turns usually need a game move.")

    player_matches_expected = None
    if expected_player is not None:
        player_matches_expected = player == expected_player
        if not player_matches_expected:
            warnings.append(f"player mismatch: expected {expected_player!r}, got {player!r}.")

    if quarantine_records is not None:
        decision = gate_move(
            records,
            quarantine_records,
            command,
            min_player_interval_seconds=min_player_interval_seconds,
            season_scoring=season_scoring,
            season=season,
            invalid_strikes_to_disqualify=invalid_strikes_to_disqualify,
            canonical_branch=canonical_branch,
            quarantine_branch=quarantine_branch,
        )
        verdict = decision.verdict
        accepted = decision.accepted and player_matches_expected is not False
        route = {
            "accepted": decision.accepted,
            "branch": decision.branch,
            "reason": decision.reason,
            "strikes_before": decision.strikes_before,
            "strikes_after": decision.strikes_after,
        }
    else:
        from .intake import validate_move

        _state, raw_verdict = validate_move(
            transcript_path,
            command,
            min_player_interval_seconds=min_player_interval_seconds,
            season_scoring=season_scoring,
            season=season,
        )
        display_verdict = redact_verdict(raw_verdict, reveal_policy=reveal_policy)
        verdict = display_verdict.to_dict()
        accepted = raw_verdict.kind != "invalid" and player_matches_expected is not False
        route = None

    if not accepted and player_matches_expected is False:
        status = "player_mismatch"
    elif accepted:
        status = "accepted"
    elif route is not None:
        status = "quarantined"
    else:
        status = "invalid"

    return {
        "accepted": accepted,
        "expected_player": expected_player,
        "ok": accepted,
        "player": player,
        "player_matches_expected": player_matches_expected,
        "route": route,
        "status": status,
        "verdict": verdict,
        "warnings": warnings,
    }


def render_submission_report(report: Mapping[str, Any]) -> str:
    lines = [
        "# Conjecture Golf Submission Check",
        "",
        f"Accepted: `{str(report['accepted']).lower()}`",
        f"Status: `{report['status']}`",
        f"Player: `{report.get('player')}`",
    ]
    if report.get("expected_player") is not None:
        lines.append(f"Expected player: `{report['expected_player']}`")
        lines.append(f"Player match: `{str(report['player_matches_expected']).lower()}`")
    route = report.get("route")
    if isinstance(route, Mapping):
        lines.extend(
            [
                "",
                "## Arena Route",
                "",
                f"- Branch: `{route['branch']}`",
                f"- Reason: `{route['reason']}`",
                f"- Invalid strikes: `{route['strikes_before']}` -> `{route['strikes_after']}`",
            ]
        )
    verdict = report["verdict"]
    if isinstance(verdict, Mapping):
        lines.extend(
            [
                "",
                "## Verdict",
                "",
                f"- Kind: `{verdict.get('kind')}`",
                f"- OK: `{str(verdict.get('ok')).lower()}`",
                f"- Score delta: `{verdict.get('score_delta')}`",
                f"- Message: {verdict.get('message')}",
            ]
        )
    warnings = report.get("warnings") or []
    if warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {item}" for item in warnings)
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check one participant JSON move without appending it.")
    parser.add_argument("transcript", help="Current JSONL transcript path")
    parser.add_argument("move", help="Move JSON path, or '-' for stdin")
    parser.add_argument("--expected-player", help="Require the move's player field to match this player")
    parser.add_argument("--min-player-interval-seconds", type=int, default=0)
    parser.add_argument("--no-season-scoring", action="store_true")
    parser.add_argument("--season", help="Optional data-only season spec path")
    parser.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    parser.add_argument("--quarantine", help="Optional quarantine JSONL path for arena-gate routing")
    parser.add_argument("--invalid-strikes-to-disqualify", type=int, default=DEFAULT_INVALID_STRIKES_TO_DISQUALIFY)
    parser.add_argument("--canonical-branch", default=DEFAULT_CANONICAL_BRANCH)
    parser.add_argument("--quarantine-branch", default=DEFAULT_QUARANTINE_BRANCH)
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    args = parser.parse_args(argv)

    try:
        season = load_optional_compiled_season(args.season)
        move = load_move(args.move)
        quarantine_records = iter_quarantine_jsonl(args.quarantine) if args.quarantine else None
        report = check_submission(
            args.transcript,
            move,
            expected_player=args.expected_player,
            min_player_interval_seconds=args.min_player_interval_seconds,
            season_scoring=not args.no_season_scoring,
            season=season,
            reveal_policy=args.reveal_policy,
            quarantine_records=quarantine_records,
            invalid_strikes_to_disqualify=args.invalid_strikes_to_disqualify,
            canonical_branch=args.canonical_branch,
            quarantine_branch=args.quarantine_branch,
        )
    except ValidationError as exc:
        report = _invalid_report(str(exc), expected_player=args.expected_player)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_submission_report(report))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
