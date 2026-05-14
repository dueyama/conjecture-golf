"""Render leaderboards from one or more transcript files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .replay import ReplayState, iter_jsonl, replay_records
from .score import leaderboard_rows, render_markdown


def replay_many(
    paths: list[str],
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = False,
) -> ReplayState:
    from .replay import apply_command

    state = ReplayState()
    for path in paths:
        for record in iter_jsonl(path):
            apply_command(
                state,
                record,
                min_player_interval_seconds=min_player_interval_seconds,
                season_scoring=season_scoring,
            )
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a Conjecture Golf leaderboard from transcripts.")
    parser.add_argument("paths", nargs="+", help="JSONL transcript paths")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    parser.add_argument(
        "--min-player-interval-seconds",
        type=int,
        default=0,
        help="Reject commands from the same player submitted sooner than this many seconds apart.",
    )
    parser.add_argument("--season-scoring", action="store_true", help="Reward only novel season progress.")
    args = parser.parse_args(argv)
    state = replay_many(
        args.paths,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=args.season_scoring,
    )
    rows = leaderboard_rows(state.scores)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(rows))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
