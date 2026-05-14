"""Render deterministic observer commentary from public transcripts."""

from __future__ import annotations

import argparse
import html
from collections.abc import Iterable, Mapping
from typing import Any

from .replay import ReplayState, apply_command, iter_jsonl
from .score import leaderboard_rows, render_markdown
from .verify import redact_verdict


def _command_label(command: Mapping[str, Any]) -> str:
    command_type = command.get("type")
    if command_type == "conjecture":
        nested = command.get("conjecture")
        nested_name = nested.get("name") if isinstance(nested, Mapping) else None
        return str(command.get("name") or nested_name or "unnamed conjecture")
    if command_type == "counterexample":
        return f"counterexample against {command.get('against', 'unknown')}"
    return str(command_type or "unknown")


def _move_summary(move_no: int, command: Mapping[str, Any], verdict: Any) -> list[str]:
    player = verdict.player or str(command.get("player") or "anonymous")
    label = _command_label(command)
    details = verdict.details or {}
    lines = [f"### Move {move_no}: `{player}`"]

    if verdict.kind == "conjecture" and verdict.ok:
        lines.append(f"- Claim kind: `{details.get('claim_kind', 'sufficient')}`.")
        lines.append(
            f"- Submitted `{label}`. It held on the verifier check for "
            f"{details.get('coverage', 'unknown')} triggering neighborhoods."
        )
        if "season_new_obligations" in details:
            lines.append(
                f"- Season novelty: `{details.get('season_new_obligations')}` new obligations, "
                f"`{details.get('season_known_obligations', 0)}` already known."
            )
        lines.append(
            f"- Score: `{verdict.score_delta}`. Complexity: `{details.get('complexity', 'unknown')}`."
        )
        return lines

    if verdict.kind == "conjecture":
        lines.append(f"- Claim kind: `{details.get('claim_kind', 'sufficient')}`.")
        lines.append(f"- Submitted `{label}`, but the verifier refuted it.")
        counterexample = details.get("counterexample")
        if isinstance(counterexample, Mapping):
            lines.append(
                f"- The failed cell expected `{counterexample.get('expected')}` "
                f"and actually became `{counterexample.get('actual')}`."
            )
        elif details.get("counterexample_redacted"):
            summary = details.get("counterexample_summary") or {}
            if isinstance(summary, Mapping):
                lines.append(
                    f"- A witness exists but is redacted. It expected `{summary.get('expected')}` "
                    f"and actually became `{summary.get('actual')}`."
                )
        lines.append(f"- Score: `{verdict.score_delta}`.")
        return lines

    if verdict.kind == "counterexample" and verdict.ok:
        lines.append(f"- Found a valid {label}.")
        lines.append(
            f"- The board uses the public rule to make `{details.get('expected')}` fail as "
            f"`{details.get('actual')}` at cell `{details.get('cell')}`."
        )
        if details.get("season_score_basis") == "verifier_revealed_counterexample":
            lines.append("- Season scoring discounts this because it matches the verifier-revealed example.")
        elif details.get("season_score_basis") == "already_countered":
            lines.append("- Season scoring discounts this because the conjecture was already refuted.")
        lines.append(f"- Minimality bonus: `{details.get('minimality_bonus', 0)}`.")
        return lines

    if verdict.kind == "score":
        lines.append("- Requested the current leaderboard.")
        return lines

    if details.get("reason") == "player_cooldown":
        lines.append("- Rejected by the per-player cooldown rule.")
        lines.append(
            f"- Elapsed: `{details.get('elapsed_seconds')}` seconds; required: "
            f"`{details.get('required_seconds')}` seconds."
        )
        return lines

    lines.append(f"- Rejected: {verdict.message}")
    lines.append(f"- Score: `{verdict.score_delta}`.")
    return lines


def _interesting_points(state: ReplayState) -> list[str]:
    valid_conjectures = [v for v in state.verdicts if v.kind == "conjecture" and v.ok]
    false_conjectures = [v for v in state.verdicts if v.kind == "conjecture" and not v.ok]
    valid_counterexamples = [v for v in state.verdicts if v.kind == "counterexample" and v.ok]
    novel_season_conjectures = [
        v for v in valid_conjectures if (v.details or {}).get("season_new_obligations", 0) > 0
    ]
    cooldown_rejections = [
        v for v in state.verdicts if (v.details or {}).get("reason") == "player_cooldown"
    ]

    points: list[str] = []
    if valid_conjectures:
        strongest = max(valid_conjectures, key=lambda v: v.score_delta)
        points.append(
            f"`{strongest.player}` had the strongest accepted conjecture in this transcript "
            f"with `{strongest.score_delta}` points."
        )
    if novel_season_conjectures:
        freshest = max(novel_season_conjectures, key=lambda v: (v.details or {}).get("season_new_obligations", 0))
        points.append(
            f"`{freshest.player}` opened the most new season territory with "
            f"`{(freshest.details or {}).get('season_new_obligations')}` new obligations."
        )
    if false_conjectures and valid_counterexamples:
        points.append(
            "The transcript has a readable conjecture-counterexample arc: broad claims create openings, "
            "and compact boards can expose the missing condition."
        )
    if cooldown_rejections:
        points.append(
            "At least one command was rejected by cooldown, so the arena can stay open without rewarding spam."
        )
    if not points:
        points.append("No dramatic swing appeared yet; more submitted conjectures would make the arena easier to read.")
    return points


def render_report(
    records: Iterable[Mapping[str, Any]],
    *,
    title: str = "Conjecture Golf Observer Report",
    min_player_interval_seconds: int = 0,
    season_scoring: bool = False,
    reveal_policy: str = "full",
) -> str:
    state = ReplayState()
    lines = [f"# {title}", ""]
    for move_no, command in enumerate(records, start=1):
        verdict = apply_command(
            state,
            command,
            min_player_interval_seconds=min_player_interval_seconds,
            season_scoring=season_scoring,
        )
        display_verdict = redact_verdict(verdict, reveal_policy=reveal_policy)
        lines.extend(_move_summary(move_no, command, display_verdict))
        lines.append("")

    lines.extend(["## Leaderboard", "", render_markdown(leaderboard_rows(state.scores)), ""])
    lines.extend(["## Interesting Points", ""])
    lines.extend(f"- {point}" for point in _interesting_points(state))
    lines.extend(
        [
            "",
            "## Commentator Note",
            "",
            "This report is deterministic commentary generated from the public transcript. "
            "A separate AI commentator may quote or expand it, but the verifier and replay remain the judge.",
        ]
    )
    return "\n".join(lines)


def _board_html(board: Any, *, highlight: Any = None) -> str:
    if not isinstance(board, list) or not all(isinstance(row, str) for row in board):
        return ""
    highlight_cell = tuple(highlight) if isinstance(highlight, list) and len(highlight) == 2 else None
    rows: list[str] = ['<div class="board" aria-label="5 by 5 board">']
    for row_index, row in enumerate(board):
        for col_index, symbol in enumerate(row):
            classes = ["cell", f"symbol-{symbol if symbol != '.' else 'empty'}"]
            if highlight_cell == (row_index, col_index):
                classes.append("highlight")
            label = {"F": "F", "W": "W", "S": "S", ".": ""}.get(symbol, symbol)
            rows.append(f'<div class="{" ".join(classes)}">{html.escape(label)}</div>')
    rows.append("</div>")
    return "\n".join(rows)


def _move_html(move_no: int, command: Mapping[str, Any], verdict: Any) -> str:
    summary_lines = _move_summary(move_no, command, verdict)
    title = html.escape(summary_lines[0].replace("### ", ""))
    body = "\n".join(
        f"<p>{html.escape(line[2:] if line.startswith('- ') else line)}</p>"
        for line in summary_lines[1:]
    )
    details = verdict.details or {}
    boards = ""
    if verdict.kind == "counterexample" and verdict.ok:
        before = details.get("before")
        after = details.get("after")
        cell = details.get("cell")
        boards = "\n".join(
            [
                '<div class="boards">',
                '<section><h4>Before</h4>',
                _board_html(before, highlight=cell),
                "</section>",
                '<section><h4>After</h4>',
                _board_html(after, highlight=cell),
                "</section>",
                "</div>",
            ]
        )
    status = "ok" if verdict.ok else "bad"
    return f'<article class="move {status}"><h3>{title}</h3>{body}{boards}</article>'


def _leaderboard_html(rows: list[dict[str, Any]]) -> str:
    headers = ["rank", "player", "total", "laws", "counterexamples", "invalid", "avg complexity"]
    out = ["<table>", "<thead><tr>"]
    out.extend(f"<th>{html.escape(header)}</th>" for header in headers)
    out.extend(["</tr></thead>", "<tbody>"])
    for idx, row in enumerate(rows, start=1):
        out.append("<tr>")
        values = [
            idx,
            row["player"],
            row["total"],
            row["law_score"],
            row["counterexample_score"],
            row["invalid_penalty"],
            row["avg_complexity"],
        ]
        out.extend(f"<td>{html.escape(str(value))}</td>" for value in values)
        out.append("</tr>")
    out.extend(["</tbody>", "</table>"])
    return "\n".join(out)


def render_html_report(
    records: Iterable[Mapping[str, Any]],
    *,
    title: str = "Conjecture Golf Observer Report",
    min_player_interval_seconds: int = 0,
    season_scoring: bool = False,
    reveal_policy: str = "full",
) -> str:
    state = ReplayState()
    moves: list[str] = []
    for move_no, command in enumerate(records, start=1):
        verdict = apply_command(
            state,
            command,
            min_player_interval_seconds=min_player_interval_seconds,
            season_scoring=season_scoring,
        )
        display_verdict = redact_verdict(verdict, reveal_policy=reveal_policy)
        moves.append(_move_html(move_no, command, display_verdict))

    rows = leaderboard_rows(state.scores)
    points = "\n".join(f"<li>{html.escape(point)}</li>" for point in _interesting_points(state))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{ color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f6f7f9; color: #18202a; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 32px 20px 56px; }}
    h1 {{ margin: 0 0 20px; font-size: 32px; }}
    h2 {{ margin-top: 34px; border-bottom: 1px solid #d9dee7; padding-bottom: 8px; }}
    .move {{ background: white; border: 1px solid #dfe5ee; border-left: 5px solid #8a96a8; border-radius: 8px; padding: 16px; margin: 14px 0; box-shadow: 0 1px 2px rgba(16, 24, 40, .04); }}
    .move.ok {{ border-left-color: #2f8f5b; }}
    .move.bad {{ border-left-color: #ba3a3a; }}
    .move h3 {{ margin: 0 0 10px; font-size: 18px; }}
    .move p {{ margin: 7px 0; line-height: 1.45; }}
    .boards {{ display: flex; flex-wrap: wrap; gap: 24px; margin-top: 14px; }}
    .boards h4 {{ margin: 0 0 8px; }}
    .board {{ display: grid; grid-template-columns: repeat(5, 34px); gap: 4px; }}
    .cell {{ width: 34px; height: 34px; display: grid; place-items: center; border-radius: 6px; border: 1px solid #cfd6e1; font-weight: 700; }}
    .symbol-empty {{ background: #f1f3f6; }}
    .symbol-F {{ background: #b7e4c7; color: #1b5e35; }}
    .symbol-W {{ background: #bde0fe; color: #174c7c; }}
    .symbol-S {{ background: #c7ccd4; color: #2f3640; }}
    .highlight {{ outline: 3px solid #d94848; outline-offset: 1px; }}
    table {{ border-collapse: collapse; width: 100%; background: white; border: 1px solid #dfe5ee; }}
    th, td {{ border-bottom: 1px solid #e5eaf1; padding: 9px 10px; text-align: right; }}
    th:nth-child(2), td:nth-child(2) {{ text-align: left; }}
    th {{ background: #edf1f6; }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(title)}</h1>
    <section>
      <h2>Moves</h2>
      {"".join(moves)}
    </section>
    <section>
      <h2>Leaderboard</h2>
      {_leaderboard_html(rows)}
    </section>
    <section>
      <h2>Interesting Points</h2>
      <ul>{points}</ul>
    </section>
  </main>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a human-readable observer report from a transcript.")
    parser.add_argument("path", help="JSONL transcript path")
    parser.add_argument("--format", choices=["markdown", "html"], default="markdown")
    parser.add_argument(
        "--min-player-interval-seconds",
        type=int,
        default=0,
        help="Apply the same per-player cooldown rule used by replay.",
    )
    parser.add_argument("--season-scoring", action="store_true", help="Apply season novelty scoring.")
    parser.add_argument("--reveal-policy", choices=["full", "redacted"], default="full")
    args = parser.parse_args(argv)
    renderer = render_html_report if args.format == "html" else render_report
    print(
        renderer(
            iter_jsonl(args.path),
            min_player_interval_seconds=args.min_player_interval_seconds,
            season_scoring=args.season_scoring,
            reveal_policy=args.reveal_policy,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
