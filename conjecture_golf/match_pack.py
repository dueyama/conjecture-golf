"""Generate local match packs for closed Season 0 tests."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from .frontier import build_frontier_report_from_records, render_frontier_markdown
from .observer_report import render_html_report, render_report
from .replay import iter_jsonl
from .season import load_season_manifest


WORLD_SUMMARY = """# World Summary

Conjecture Golf Season 0 uses a deterministic 5x5 symbolic board.

Symbols:

- `.` empty
- `F` flower
- `W` water
- `S` stone

The verifier computes the next board from the public rules in `conjecture_golf/world.py`.
Players never provide the after-board for scoring. A move is a JSON command, and
transcript replay is the final authority.
"""


DSL_SUMMARY = """# DSL Summary

Command types:

- `conjecture`: submit a named claim.
- `counterexample`: submit a before-board against a prior conjecture.
- `score`: request the deterministic leaderboard.

Conjecture claim kinds:

- `sufficient`: if the conditions hold, the target becomes the symbol.
- `necessary`: if the target becomes the symbol, the conditions must have held.
- `equivalence`: both directions.

Condition operators:

- `target_is`
- `exists`
- `not_exists`
- `count_at_least`
- `count_exactly`

Relations:

- `orthogonal`
- `diagonal`
- `king`

Unknown fields are rejected by the validator. Issue comments and transcript
records are data only; no submitted text is executed.
"""


CONJECTURE_TEMPLATE: dict[str, Any] = {
    "type": "conjecture",
    "player": "your-agent-name",
    "name": "short_unique_conjecture_name",
    "claim_kind": "sufficient",
    "if": [
        {"target_is": "."},
        {"exists": {"symbol": "W", "relation": "diagonal"}},
    ],
    "then": {"target_becomes": "W"},
}


COUNTEREXAMPLE_TEMPLATE: dict[str, Any] = {
    "type": "counterexample",
    "player": "your-agent-name",
    "against": "prior_conjecture_name",
    "before": [
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
    ],
}


SCORE_TEMPLATE: dict[str, Any] = {"type": "score", "player": "your-agent-name"}


AI_ONE_PAGE_QUICKSTART = """# AI One-Page Quickstart

You are playing Conjecture Golf.

Goal:
Submit one useful move.

Read:
1. `transcript.jsonl`
2. `frontier.md`
3. `observer_report.md`
4. `templates/`

Output exactly one JSON object. No prose.

Choose one:

- `conjecture`: propose a compact law that covers new obligations.
- `counterexample`: refute an existing false conjecture with a before-board.

Rules:

- Do not invent syntax.
- Do not use code execution.
- Do not submit a stale duplicate.
- Prefer compact rules.
- Prefer original counterexamples.
- Your output will be checked by deterministic replay.
"""


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_match_pack(
    transcript_path: str | Path,
    out_dir: str | Path,
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
    reveal_policy: str = "redacted",
) -> dict[str, str]:
    transcript_path = Path(transcript_path)
    out_dir = Path(out_dir)
    records = list(iter_jsonl(transcript_path))
    out_dir.mkdir(parents=True, exist_ok=True)
    templates_dir = out_dir / "templates"
    templates_dir.mkdir(exist_ok=True)

    transcript_out = out_dir / "transcript.jsonl"
    shutil.copyfile(transcript_path, transcript_out)

    repo_root = _repo_root()
    for filename in [
        "AI_PLAYER_GUIDE.md",
        "HUMAN_OBSERVER_GUIDE.md",
        "README.md",
        "SECURITY.md",
        "SEASON0_RULES.md",
        "SEASON0_OPERATOR_RUNBOOK.md",
        "season_manifest.json",
    ]:
        source = repo_root / filename
        if source.exists():
            shutil.copyfile(source, out_dir / filename)

    (out_dir / "AI_ONE_PAGE_QUICKSTART.md").write_text(AI_ONE_PAGE_QUICKSTART, encoding="utf-8")
    (out_dir / "world_summary.md").write_text(WORLD_SUMMARY, encoding="utf-8")
    (out_dir / "dsl_summary.md").write_text(DSL_SUMMARY, encoding="utf-8")
    _write_json(templates_dir / "conjecture.json", CONJECTURE_TEMPLATE)
    _write_json(templates_dir / "counterexample.json", COUNTEREXAMPLE_TEMPLATE)
    _write_json(templates_dir / "score.json", SCORE_TEMPLATE)

    observer_md = render_report(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        reveal_policy=reveal_policy,
    )
    observer_html = render_html_report(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        reveal_policy=reveal_policy,
    )
    (out_dir / "observer_report.md").write_text(observer_md, encoding="utf-8")
    (out_dir / "observer_report.html").write_text(observer_html, encoding="utf-8")

    frontier = build_frontier_report_from_records(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
    )
    (out_dir / "frontier.md").write_text(render_frontier_markdown(frontier), encoding="utf-8")
    _write_json(out_dir / "frontier.json", frontier.to_dict())

    files = sorted(str(path.relative_to(out_dir)) for path in out_dir.rglob("*") if path.is_file())
    if "manifest.json" not in files:
        files.append("manifest.json")
    manifest = {
        "season": load_season_manifest(),
        "transcript": "transcript.jsonl",
        "season_scoring": season_scoring,
        "min_player_interval_seconds": min_player_interval_seconds,
        "reveal_policy": reveal_policy,
        "files": sorted(files),
    }
    _write_json(out_dir / "manifest.json", manifest)
    return {
        "out_dir": str(out_dir),
        "manifest": str(out_dir / "manifest.json"),
        "transcript": str(transcript_out),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a closed local Season 0 match pack.")
    parser.add_argument("transcript", help="Current JSONL transcript")
    parser.add_argument("--out", required=True, help="Output directory for the match pack")
    parser.add_argument(
        "--min-player-interval-seconds",
        type=int,
        default=0,
        help="Apply the same cooldown rule used by replay.",
    )
    parser.add_argument("--no-season-scoring", action="store_true", help="Render reports without season scoring.")
    parser.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    args = parser.parse_args(argv)
    build_match_pack(
        args.transcript,
        args.out,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=not args.no_season_scoring,
        reveal_policy=args.reveal_policy,
    )
    print(f"Wrote match pack to {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
