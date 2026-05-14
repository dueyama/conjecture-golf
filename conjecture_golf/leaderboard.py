"""Render leaderboards from one or more transcript files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .replay import ReplayState, iter_jsonl, replay_records
from .score import apply_verdict, leaderboard_rows, render_markdown


def replay_many(paths: list[str]) -> ReplayState:
    from .replay import apply_command

    state = ReplayState()
    for path in paths:
        for record in iter_jsonl(path):
            apply_command(state, record)
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a Conjecture Golf leaderboard from transcripts.")
    parser.add_argument("paths", nargs="+", help="JSONL transcript paths")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    args = parser.parse_args(argv)
    state = replay_many(args.paths)
    rows = leaderboard_rows(state.scores)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(rows))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
