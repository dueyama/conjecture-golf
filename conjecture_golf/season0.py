"""Convenience wrapper for local Season 0 operations."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from .frontier import build_frontier_report_from_records, render_frontier_markdown
from .intake import append_move, load_move, prepare_move, validate_move
from .match_pack import build_match_pack
from .observer_report import render_html_report, render_report
from .replay import iter_jsonl, replay_file
from .score import leaderboard_rows, render_markdown
from .season_eval import evaluate_records, render_evaluation_markdown


def _cmd_init(args: argparse.Namespace) -> int:
    source = Path(args.source)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, out)
    print(f"Wrote Season 0 transcript: {out}")
    return 0


def _cmd_pack(args: argparse.Namespace) -> int:
    build_match_pack(
        args.transcript,
        args.out,
        min_player_interval_seconds=args.min_player_interval_seconds,
        reveal_policy=args.reveal_policy,
    )
    print(f"Wrote match pack to {args.out}")
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    move = prepare_move(load_move(args.move), player=args.player)
    _state, verdict = validate_move(
        args.transcript,
        move,
        min_player_interval_seconds=args.min_player_interval_seconds,
    )
    print(json.dumps(verdict.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    if verdict.kind == "invalid":
        return 1
    if args.append:
        append_move(args.transcript, move)
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    records = list(iter_jsonl(args.transcript))

    state = replay_file(args.transcript, season_scoring=True)
    (out / "leaderboard.md").write_text(render_markdown(leaderboard_rows(state.scores)) + "\n", encoding="utf-8")

    frontier = build_frontier_report_from_records(records)
    (out / "frontier.md").write_text(render_frontier_markdown(frontier), encoding="utf-8")

    (out / "observer_report.md").write_text(
        render_report(records, season_scoring=True, reveal_policy=args.reveal_policy),
        encoding="utf-8",
    )
    (out / "observer_report.html").write_text(
        render_html_report(records, season_scoring=True, reveal_policy=args.reveal_policy),
        encoding="utf-8",
    )

    evaluation = evaluate_records(records)
    (out / "season_eval.md").write_text(render_evaluation_markdown(evaluation), encoding="utf-8")
    print(f"Wrote Season 0 reports to {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Season 0 local operations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a local Season 0 transcript.")
    init.add_argument("--out", required=True, help="Output transcript path")
    init.add_argument("--source", default="examples/transcripts/basic.jsonl", help="Seed transcript path")
    init.set_defaults(func=_cmd_init)

    pack = subparsers.add_parser("pack", help="Generate a match pack.")
    pack.add_argument("transcript", help="Transcript path")
    pack.add_argument("--out", required=True, help="Output directory")
    pack.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    pack.add_argument("--min-player-interval-seconds", type=int, default=0)
    pack.set_defaults(func=_cmd_pack)

    apply = subparsers.add_parser("apply", help="Validate and optionally append a move.")
    apply.add_argument("transcript", help="Transcript path")
    apply.add_argument("move", help="Move JSON path")
    apply.add_argument("--player", help="Override player name")
    apply.add_argument("--append", action="store_true", help="Append when not rejected as invalid")
    apply.add_argument("--min-player-interval-seconds", type=int, default=0)
    apply.set_defaults(func=_cmd_apply)

    report = subparsers.add_parser("report", help="Write replay, frontier, observer, and eval reports.")
    report.add_argument("transcript", help="Transcript path")
    report.add_argument("--out", required=True, help="Output report directory")
    report.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    report.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
