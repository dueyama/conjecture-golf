"""Open-arena branch gate for public Conjecture Golf play.

The game should be open to unknown participants without letting low-quality or
spammy commands distort the canonical match. This gate routes valid game moves
to the canonical transcript branch and rejected moves to a quarantine branch.
It does not run git itself; workflows can use the deterministic decision.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dsl import player_name_from_submission
from .intake import append_move, load_move
from .replay import apply_command, iter_jsonl, replay_records
from .season_catalog import load_optional_compiled_season
from .season_engine import CompiledSeason
from .verify import Verdict

DEFAULT_CANONICAL_BRANCH = "arena/season-0"
DEFAULT_QUARANTINE_BRANCH = "quarantine/season-0"
DEFAULT_INVALID_STRIKES_TO_DISQUALIFY = 3


@dataclass(frozen=True)
class GateDecision:
    accepted: bool
    branch: str
    player: str
    reason: str
    verdict: dict[str, Any]
    strikes_before: int
    strikes_after: int
    canonical_command: dict[str, Any] | None
    quarantine_record: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "branch": self.branch,
            "player": self.player,
            "reason": self.reason,
            "verdict": self.verdict,
            "strikes_before": self.strikes_before,
            "strikes_after": self.strikes_after,
            "canonical_command": self.canonical_command,
            "quarantine_record": self.quarantine_record,
        }


def _command_player(command: Mapping[str, Any]) -> str:
    if command.get("type") == "conjecture" and isinstance(command.get("conjecture"), Mapping):
        nested = dict(command["conjecture"])
        if "player" not in nested and "player" in command:
            nested["player"] = command["player"]
        return player_name_from_submission(nested)
    return player_name_from_submission(command)


def _invalid_verdict(player: str, message: str, *, reason: str) -> Verdict:
    return Verdict(
        ok=False,
        kind="invalid",
        player=player,
        message=message,
        score_delta=0,
        details={"reason": reason},
    )


def _quarantine_record(
    *,
    player: str,
    command: Mapping[str, Any],
    verdict: Verdict,
    reason: str,
    canonical_branch: str,
    quarantine_branch: str,
    strikes_after: int,
) -> dict[str, Any]:
    return {
        "type": "quarantine",
        "player": player,
        "reason": reason,
        "canonical_branch": canonical_branch,
        "quarantine_branch": quarantine_branch,
        "strikes_after": strikes_after,
        "verdict": verdict.to_dict(),
        "command": dict(command),
    }


def invalid_strikes_for_player(quarantine_records: Iterable[Mapping[str, Any]], player: str) -> int:
    strikes = 0
    for record in quarantine_records:
        if record.get("type") != "quarantine":
            continue
        if record.get("player") != player:
            continue
        verdict = record.get("verdict")
        if isinstance(verdict, Mapping) and verdict.get("kind") == "invalid":
            strikes += 1
    return strikes


def gate_move(
    canonical_records: Iterable[Mapping[str, Any]],
    quarantine_records: Iterable[Mapping[str, Any]],
    command: Mapping[str, Any],
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
    season: CompiledSeason | None = None,
    invalid_strikes_to_disqualify: int = DEFAULT_INVALID_STRIKES_TO_DISQUALIFY,
    canonical_branch: str = DEFAULT_CANONICAL_BRANCH,
    quarantine_branch: str = DEFAULT_QUARANTINE_BRANCH,
) -> GateDecision:
    if invalid_strikes_to_disqualify < 1:
        raise ValueError("invalid_strikes_to_disqualify must be at least 1")

    canonical_records = list(canonical_records)
    quarantine_records = list(quarantine_records)
    command = dict(command)
    player = _command_player(command)
    strikes_before = invalid_strikes_for_player(quarantine_records, player)
    if strikes_before >= invalid_strikes_to_disqualify:
        verdict = _invalid_verdict(
            player,
            f"Player {player!r} is disqualified from the canonical branch for this season.",
            reason="player_disqualified",
        )
        record = _quarantine_record(
            player=player,
            command=command,
            verdict=verdict,
            reason="player_disqualified",
            canonical_branch=canonical_branch,
            quarantine_branch=quarantine_branch,
            strikes_after=strikes_before,
        )
        return GateDecision(
            accepted=False,
            branch=quarantine_branch,
            player=player,
            reason="player_disqualified",
            verdict=verdict.to_dict(),
            strikes_before=strikes_before,
            strikes_after=strikes_before,
            canonical_command=None,
            quarantine_record=record,
        )

    state = replay_records(
        canonical_records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )
    verdict = apply_command(
        state,
        command,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )
    if verdict.kind != "invalid":
        return GateDecision(
            accepted=True,
            branch=canonical_branch,
            player=player,
            reason="accepted_for_canonical_transcript",
            verdict=verdict.to_dict(),
            strikes_before=strikes_before,
            strikes_after=strikes_before,
            canonical_command=command,
            quarantine_record=None,
        )

    strikes_after = strikes_before + 1
    reason = "invalid_move"
    if strikes_after >= invalid_strikes_to_disqualify:
        reason = "invalid_move_player_disqualified"
    record = _quarantine_record(
        player=player,
        command=command,
        verdict=verdict,
        reason=reason,
        canonical_branch=canonical_branch,
        quarantine_branch=quarantine_branch,
        strikes_after=strikes_after,
    )
    return GateDecision(
        accepted=False,
        branch=quarantine_branch,
        player=player,
        reason=reason,
        verdict=verdict.to_dict(),
        strikes_before=strikes_before,
        strikes_after=strikes_after,
        canonical_command=None,
        quarantine_record=record,
    )


def iter_quarantine_jsonl(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid quarantine JSON on line {line_no}: {exc.msg}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"quarantine line {line_no} must be a JSON object")
            records.append(payload)
    return records


def append_quarantine_record(path: str | Path, record: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route one public move to canonical or quarantine branch data.")
    parser.add_argument("canonical_transcript", help="Canonical JSONL transcript path")
    parser.add_argument("move", help="Move JSON path, or '-' for stdin")
    parser.add_argument("--quarantine", required=True, help="Quarantine JSONL path")
    parser.add_argument("--append", action="store_true", help="Append to the routed transcript file.")
    parser.add_argument("--strict-exit", action="store_true", help="Return non-zero for quarantine decisions.")
    parser.add_argument("--min-player-interval-seconds", type=int, default=0)
    parser.add_argument("--no-season-scoring", action="store_true")
    parser.add_argument("--season", help="Optional data-only season spec path")
    parser.add_argument("--invalid-strikes-to-disqualify", type=int, default=DEFAULT_INVALID_STRIKES_TO_DISQUALIFY)
    parser.add_argument("--canonical-branch", default=DEFAULT_CANONICAL_BRANCH)
    parser.add_argument("--quarantine-branch", default=DEFAULT_QUARANTINE_BRANCH)
    args = parser.parse_args(argv)

    canonical_path = Path(args.canonical_transcript)
    canonical_records = list(iter_jsonl(canonical_path)) if canonical_path.exists() else []
    quarantine_records = iter_quarantine_jsonl(args.quarantine)
    season = load_optional_compiled_season(args.season)
    decision = gate_move(
        canonical_records,
        quarantine_records,
        load_move(args.move),
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=not args.no_season_scoring,
        season=season,
        invalid_strikes_to_disqualify=args.invalid_strikes_to_disqualify,
        canonical_branch=args.canonical_branch,
        quarantine_branch=args.quarantine_branch,
    )
    if args.append:
        if decision.accepted and decision.canonical_command is not None:
            append_move(canonical_path, decision.canonical_command)
        elif decision.quarantine_record is not None:
            append_quarantine_record(args.quarantine, decision.quarantine_record)
    print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    if args.strict_exit and not decision.accepted:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
