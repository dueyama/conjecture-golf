"""Local move intake for closed Season 0 tests.

The intake command validates JSON moves by replaying the public transcript and
then applying the candidate move. It never executes submitted text.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .replay import ReplayState, apply_command, iter_jsonl, replay_records
from .season_catalog import load_optional_compiled_season
from .season_engine import CompiledSeason
from .verify import redact_verdict
from .world import ValidationError


def load_move(path: str | Path) -> dict[str, Any]:
    if str(path) == "-":
        raw = sys.stdin.read()
    else:
        raw = Path(path).read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"move file is not valid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValidationError("move must be a JSON object")
    return payload


def prepare_move(payload: Mapping[str, Any], *, player: str | None = None) -> dict[str, Any]:
    move = dict(payload)
    if player is None:
        return move
    move["player"] = player
    if move.get("type") == "conjecture" and isinstance(move.get("conjecture"), Mapping):
        nested = dict(move["conjecture"])
        nested["player"] = player
        move["conjecture"] = nested
    return move


def append_move(path: str | Path, move: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(dict(move), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def validate_move(
    transcript_path: str | Path,
    move: Mapping[str, Any],
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
    season: CompiledSeason | None = None,
) -> tuple[ReplayState, Any]:
    transcript_path = Path(transcript_path)
    records = list(iter_jsonl(transcript_path)) if transcript_path.exists() else []
    state = replay_records(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )
    verdict = apply_command(
        state,
        move,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )
    return state, verdict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and optionally append a local Conjecture Golf move.")
    parser.add_argument("transcript", help="JSONL transcript path")
    parser.add_argument("move", help="Move JSON path, or '-' for stdin")
    parser.add_argument("--player", help="Override the move player name")
    parser.add_argument("--append", action="store_true", help="Append the move when it is not rejected as invalid")
    parser.add_argument(
        "--min-player-interval-seconds",
        type=int,
        default=0,
        help="Apply the same cooldown rule used by replay.",
    )
    parser.add_argument("--no-season-scoring", action="store_true", help="Validate without season scoring.")
    parser.add_argument("--reveal-policy", choices=["full", "redacted"], default="full")
    parser.add_argument("--season", help="Optional data-only season spec path")
    args = parser.parse_args(argv)

    try:
        season = load_optional_compiled_season(args.season)
        move = prepare_move(load_move(args.move), player=args.player)
        _state, verdict = validate_move(
            args.transcript,
            move,
            min_player_interval_seconds=args.min_player_interval_seconds,
            season_scoring=not args.no_season_scoring,
            season=season,
        )
    except ValidationError as exc:
        verdict = {
            "ok": False,
            "kind": "invalid",
            "player": args.player,
            "message": str(exc),
            "score_delta": -5,
            "details": {"reason": "invalid_move_json"},
        }
        print(json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True))
        return 1

    display = redact_verdict(verdict, reveal_policy=args.reveal_policy)
    print(json.dumps(display.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))

    if verdict.kind == "invalid":
        return 1
    if args.append:
        append_move(args.transcript, move)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
