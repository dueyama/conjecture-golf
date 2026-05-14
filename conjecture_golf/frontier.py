"""Obligation frontier diagnostics for Season 0.

The frontier report exposes aggregate public coverage only. It does not reveal
local obligation IDs or hidden witnesses, so players can use it as a strategic
map without turning it into a solution oracle.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .obligations import all_local_obligation_ids, summarize_obligation_ids
from .replay import ReplayState, iter_jsonl, replay_records
from .season import season_id


@dataclass(frozen=True)
class FrontierReport:
    total_obligations: int
    covered_obligations: int
    uncovered_obligations: int
    coverage_ratio: float
    covered_summary: dict[str, Any]
    uncovered_summary: dict[str, Any]
    open_frontier: list[dict[str, Any]]
    covered_areas: list[dict[str, Any]]
    stale_traps: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_obligations": self.total_obligations,
            "covered_obligations": self.covered_obligations,
            "uncovered_obligations": self.uncovered_obligations,
            "coverage_ratio": self.coverage_ratio,
            "covered_summary": self.covered_summary,
            "uncovered_summary": self.uncovered_summary,
            "open_frontier": self.open_frontier,
            "covered_areas": self.covered_areas,
            "stale_traps": self.stale_traps,
        }


def _top_areas(summary: Mapping[str, Any], *, limit: int = 8) -> list[dict[str, Any]]:
    items = summary.get("by_claim_and_transition", {})
    if not isinstance(items, Mapping):
        return []
    rows: list[dict[str, Any]] = []
    for key, count in items.items():
        claim_kind, transition = str(key).split(":", 1)
        rows.append({"claim_kind": claim_kind, "transition": transition, "count": int(count)})
    return sorted(rows, key=lambda row: (-row["count"], row["claim_kind"], row["transition"]))[:limit]


def _stale_traps(
    covered_summary: Mapping[str, Any],
    uncovered_summary: Mapping[str, Any],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    covered = covered_summary.get("by_claim_and_transition", {})
    uncovered = uncovered_summary.get("by_claim_and_transition", {})
    if not isinstance(covered, Mapping) or not isinstance(uncovered, Mapping):
        return []
    rows: list[dict[str, Any]] = []
    for key, covered_count_raw in covered.items():
        covered_count = int(covered_count_raw)
        open_count = int(uncovered.get(key, 0))
        total = covered_count + open_count
        if covered_count == 0 or total == 0:
            continue
        coverage_ratio = covered_count / total
        if coverage_ratio < 0.5:
            continue
        claim_kind, transition = str(key).split(":", 1)
        rows.append(
            {
                "claim_kind": claim_kind,
                "transition": transition,
                "covered": covered_count,
                "uncovered": open_count,
                "coverage_ratio": round(coverage_ratio, 6),
            }
        )
    return sorted(rows, key=lambda row: (-row["coverage_ratio"], row["uncovered"], row["claim_kind"], row["transition"]))[:limit]


def build_frontier_report(state: ReplayState) -> FrontierReport:
    universe = all_local_obligation_ids()
    covered = frozenset(item for item in state.obligation_ledger.covered if item in universe)
    uncovered = universe - covered
    covered_summary = summarize_obligation_ids(covered)
    uncovered_summary = summarize_obligation_ids(uncovered)
    total = len(universe)
    return FrontierReport(
        total_obligations=total,
        covered_obligations=len(covered),
        uncovered_obligations=len(uncovered),
        coverage_ratio=round(len(covered) / total, 6) if total else 0.0,
        covered_summary=covered_summary,
        uncovered_summary=uncovered_summary,
        open_frontier=_top_areas(uncovered_summary),
        covered_areas=_top_areas(covered_summary),
        stale_traps=_stale_traps(covered_summary, uncovered_summary),
    )


def build_frontier_report_from_records(
    records: list[Mapping[str, Any]],
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
) -> FrontierReport:
    state = replay_records(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
    )
    return build_frontier_report(state)


def render_frontier_markdown(report: FrontierReport, *, title: str = "Obligation Frontier") -> str:
    data = report.to_dict()
    lines = [
        f"# {title}",
        "",
        f"Season: `{season_id()}`",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| covered obligations | {data['covered_obligations']} |",
        f"| uncovered obligations | {data['uncovered_obligations']} |",
        f"| total obligations | {data['total_obligations']} |",
        f"| coverage ratio | {data['coverage_ratio']:.6f} |",
        "",
        "## Open Frontier",
        "",
        "| claim_kind | transition | uncovered |",
        "| --- | --- | ---: |",
    ]
    for row in report.open_frontier:
        lines.append(f"| {row['claim_kind']} | {row['transition']} | {row['count']} |")
    if not report.open_frontier:
        lines.append("| - | - | 0 |")

    lines.extend(["", "## Covered Areas", "", "| claim_kind | transition | covered |", "| --- | --- | ---: |"])
    for row in report.covered_areas:
        lines.append(f"| {row['claim_kind']} | {row['transition']} | {row['count']} |")
    if not report.covered_areas:
        lines.append("| - | - | 0 |")

    lines.extend(
        [
            "",
            "## Stale Traps",
            "",
            "| claim_kind | transition | covered | uncovered | coverage_ratio |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
    )
    for row in report.stale_traps:
        lines.append(
            f"| {row['claim_kind']} | {row['transition']} | {row['covered']} | "
            f"{row['uncovered']} | {row['coverage_ratio']:.6f} |"
        )
    if not report.stale_traps:
        lines.append("| - | - | 0 | 0 | 0.000000 |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a Season 0 obligation frontier report.")
    parser.add_argument("path", help="JSONL transcript path")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    parser.add_argument(
        "--min-player-interval-seconds",
        type=int,
        default=0,
        help="Apply the same cooldown rule used by replay.",
    )
    parser.add_argument(
        "--no-season-scoring",
        action="store_true",
        help="Replay without season scoring before computing coverage.",
    )
    args = parser.parse_args(argv)
    records = list(iter_jsonl(args.path))
    report = build_frontier_report_from_records(
        records,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=not args.no_season_scoring,
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_frontier_markdown(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
