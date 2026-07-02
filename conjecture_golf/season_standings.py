"""Deterministic season standings and title races.

This module turns a replayed transcript into explicit competitive objectives:
the scheduled championship race, secondary titles, phase, and next strategic
targets. It is presentation logic only; replay and verifier verdicts remain the
judge.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .frontier import FrontierReport, build_frontier_report
from .replay import ReplayState, iter_jsonl, replay_records
from .score import leaderboard_rows, render_markdown
from .season import season_id
from .season_catalog import load_optional_compiled_season
from .season_engine import CompiledSeason

DEFAULT_MOVE_CAP = 48
DEFAULT_COVERAGE_TARGET_RATIO = 0.55


@dataclass(frozen=True)
class TitleRace:
    key: str
    title: str
    leader: str | None
    value: int | float | None
    description: str
    contenders: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "leader": self.leader,
            "value": self.value,
            "description": self.description,
            "contenders": self.contenders,
        }


@dataclass(frozen=True)
class SeasonStandings:
    season_id: str
    total_moves: int
    move_cap: int
    moves_remaining: int
    phase: str
    season_complete: bool
    coverage_target_ratio: float
    coverage_target_met: bool
    victory_rule: str
    leaderboard: list[dict[str, Any]]
    qualified_players: list[str]
    unqualified_players: list[str]
    title_races: list[TitleRace]
    frontier: dict[str, Any]
    next_objectives: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "season_id": self.season_id,
            "total_moves": self.total_moves,
            "move_cap": self.move_cap,
            "moves_remaining": self.moves_remaining,
            "phase": self.phase,
            "season_complete": self.season_complete,
            "coverage_target_ratio": self.coverage_target_ratio,
            "coverage_target_met": self.coverage_target_met,
            "victory_rule": self.victory_rule,
            "leaderboard": self.leaderboard,
            "qualified_players": self.qualified_players,
            "unqualified_players": self.unqualified_players,
            "title_races": [race.to_dict() for race in self.title_races],
            "frontier": self.frontier,
            "next_objectives": self.next_objectives,
        }


def _empty_metrics() -> dict[str, int]:
    return {
        "new_obligations": 0,
        "necessary_obligations": 0,
        "territory_areas": 0,
        "compression_score": 0,
        "novel_counterexamples": 0,
        "stale_or_duplicate_moves": 0,
        "title_points": 0,
    }


def _player_metrics(verdicts: Iterable[Any]) -> dict[str, dict[str, int]]:
    metrics: dict[str, dict[str, int]] = defaultdict(_empty_metrics)
    territory_by_player: dict[str, set[str]] = defaultdict(set)
    for verdict in verdicts:
        player = verdict.player or "anonymous"
        details = verdict.details or {}
        basis = details.get("season_score_basis")
        if verdict.kind == "conjecture" and verdict.ok:
            new_obligations = int(details.get("season_new_obligations") or 0)
            metrics[player]["new_obligations"] += new_obligations
            counts = details.get("season_new_obligation_counts")
            if isinstance(counts, Mapping):
                metrics[player]["necessary_obligations"] += int(counts.get("necessary", 0))
            complexity = max(1, int(details.get("complexity") or 1))
            metrics[player]["compression_score"] += new_obligations // complexity
            summary = details.get("season_new_obligation_summary")
            by_area = summary.get("by_claim_and_transition") if isinstance(summary, Mapping) else None
            if isinstance(by_area, Mapping):
                territory_by_player[player].update(str(key) for key, value in by_area.items() if int(value) > 0)
        if verdict.kind == "counterexample" and verdict.ok and basis == "novel_first_counterexample":
            metrics[player]["novel_counterexamples"] += 1
        if basis in {"stale_true_conjecture", "already_countered", "duplicate_witness"}:
            metrics[player]["stale_or_duplicate_moves"] += 1
        if details.get("reason") == "duplicate_conjecture":
            metrics[player]["stale_or_duplicate_moves"] += 1
    for player, areas in territory_by_player.items():
        metrics[player]["territory_areas"] = len(areas)
    return dict(metrics)


def _qualified_players(rows: Iterable[Mapping[str, Any]]) -> set[str]:
    return {
        str(row["player"])
        for row in rows
        if int(row.get("valid_conjectures", 0)) > 0 or int(row.get("valid_counterexamples", 0)) > 0
    }


def _rank(
    rows: list[dict[str, Any]],
    *,
    value_key: str,
    lower_is_better: bool = False,
    require_positive: bool = False,
    limit: int = 3,
) -> list[dict[str, Any]]:
    candidates = []
    for row in rows:
        value = row.get(value_key, 0)
        if require_positive and value <= 0:
            continue
        candidates.append(row)
    if lower_is_better:
        ordered = sorted(candidates, key=lambda row: (row.get(value_key, 0), -row.get("total", 0), row["player"]))
    else:
        ordered = sorted(candidates, key=lambda row: (-row.get(value_key, 0), -row.get("total", 0), row["player"]))
    return [
        {
            "rank": index,
            "player": row["player"],
            "value": row.get(value_key, 0),
            "total": row.get("total", 0),
        }
        for index, row in enumerate(ordered[:limit], start=1)
    ]


def _race(
    *,
    key: str,
    title: str,
    description: str,
    contenders: list[dict[str, Any]],
) -> TitleRace:
    leader = contenders[0]["player"] if contenders else None
    value = contenders[0]["value"] if contenders else None
    return TitleRace(
        key=key,
        title=title,
        leader=leader,
        value=value,
        description=description,
        contenders=contenders,
    )


def _uses_title_points(season: CompiledSeason | None) -> bool:
    return season is not None and season.spec.competition.victory == "title_points"


def _title_point_schedule(season: CompiledSeason | None) -> dict[int, int]:
    points = season.spec.competition.title_points if season is not None else {"first": 5, "second": 3, "third": 1}
    return {
        1: int(points.get("first", 5)),
        2: int(points.get("second", 3)),
        3: int(points.get("third", 1)),
    }


def _award_title_points(
    rows: list[dict[str, Any]],
    races: list[TitleRace],
    *,
    season: CompiledSeason | None,
) -> list[dict[str, Any]]:
    by_player = {row["player"]: dict(row, title_points=0) for row in rows}
    schedule = _title_point_schedule(season)
    for race in races:
        for contender in race.contenders:
            player = contender["player"]
            if player in by_player:
                by_player[player]["title_points"] += schedule.get(int(contender["rank"]), 0)
    return [by_player[row["player"]] for row in rows]


def _phase(total_moves: int, move_cap: int, coverage_ratio: float, coverage_target_ratio: float) -> str:
    if total_moves <= 0:
        return "preseason"
    if total_moves >= move_cap:
        return "final"
    move_progress = total_moves / move_cap
    coverage_progress = coverage_ratio / coverage_target_ratio if coverage_target_ratio > 0 else 0.0
    progress = max(move_progress, coverage_progress)
    if progress < 0.25:
        return "opening"
    if progress < 0.67:
        return "midseason"
    return "endgame"


def _next_objectives(frontier: FrontierReport, rows: list[dict[str, Any]], *, victory_metric: str = "total") -> list[str]:
    objectives: list[str] = []
    for row in frontier.open_frontier[:3]:
        objectives.append(
            "Cover new "
            f"{row['claim_kind']} {row['transition']} obligations; {row['count']} remain open."
        )
    for row in frontier.stale_traps[:2]:
        objectives.append(
            "Avoid stale "
            f"{row['claim_kind']} {row['transition']} claims; "
            f"{row['covered']} are already covered and {row['uncovered']} remain."
        )
    if rows:
        leader = rows[0]
        if victory_metric == "title_points":
            objectives.append(
                f"Catch `{leader['player']}` on title points, or take a title race they do not control."
            )
        else:
            objectives.append(
                f"Catch `{leader['player']}` on total score, or take a secondary title race."
            )
    if not objectives:
        objectives.append("No frontier remains; preserve the transcript and start a new season spec.")
    return objectives


def build_season_standings(
    records: Iterable[Mapping[str, Any]],
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
    season: CompiledSeason | None = None,
    move_cap: int = DEFAULT_MOVE_CAP,
    coverage_target_ratio: float = DEFAULT_COVERAGE_TARGET_RATIO,
) -> SeasonStandings:
    state = replay_records(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )
    return build_season_standings_from_state(
        state,
        season=season,
        move_cap=move_cap,
        coverage_target_ratio=coverage_target_ratio,
    )


def build_season_standings_from_state(
    state: ReplayState,
    *,
    season: CompiledSeason | None = None,
    move_cap: int = DEFAULT_MOVE_CAP,
    coverage_target_ratio: float = DEFAULT_COVERAGE_TARGET_RATIO,
) -> SeasonStandings:
    if move_cap < 1:
        raise ValueError("move_cap must be at least 1")
    if not 0 < coverage_target_ratio <= 1:
        raise ValueError("coverage_target_ratio must be between 0 and 1")

    rows = leaderboard_rows(state.scores)
    metrics = _player_metrics(state.verdicts)
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        player = row["player"]
        extra = metrics.get(player, _empty_metrics())
        enriched_rows.append({**row, **extra})
    qualified_players = _qualified_players(enriched_rows)
    title_rows = [row for row in enriched_rows if row["player"] in qualified_players]

    frontier = build_frontier_report(state, season=season)
    total_moves = len(state.verdicts)
    moves_remaining = max(0, move_cap - total_moves)
    coverage_target_met = frontier.coverage_ratio >= coverage_target_ratio
    base_title_races = [
        _race(
            key="lawwright",
            title="Lawwright",
            description="Most points from accepted conjectures.",
            contenders=_rank(title_rows, value_key="law_score", require_positive=True),
        ),
        _race(
            key="refuter",
            title="Refuter",
            description="Most points from valid counterexamples.",
            contenders=_rank(title_rows, value_key="counterexample_score", require_positive=True),
        ),
        _race(
            key="frontier_explorer",
            title="Frontier Explorer",
            description="Most newly covered local obligations.",
            contenders=_rank(title_rows, value_key="new_obligations", require_positive=True),
        ),
        _race(
            key="territory",
            title="Territory",
            description="Most distinct claim/transition areas touched with new obligations.",
            contenders=_rank(title_rows, value_key="territory_areas", require_positive=True),
        ),
        _race(
            key="compression",
            title="Compression",
            description="Most new obligations explained per unit of conjecture complexity.",
            contenders=_rank(title_rows, value_key="compression_score", require_positive=True),
        ),
        _race(
            key="characterizer",
            title="Characterizer",
            description="Most newly covered necessary-side obligations.",
            contenders=_rank(title_rows, value_key="necessary_obligations", require_positive=True),
        ),
        _race(
            key="clean_play",
            title="Clean Play",
            description="Fewest invalid moves, with total score as the tie-breaker.",
            contenders=_rank(title_rows, value_key="invalid_moves", lower_is_better=True),
        ),
    ]
    if _uses_title_points(season):
        enriched_rows = _award_title_points(enriched_rows, base_title_races, season=season)
        enriched_rows = sorted(enriched_rows, key=lambda row: (-row.get("title_points", 0), -row.get("total", 0), row["player"]))
        title_rows = [row for row in enriched_rows if row["player"] in qualified_players]
        title_races = [
            _race(
                key="championship",
                title="Season Champion",
                description="Most title points across Season 2 races, with raw score as the tie-breaker.",
                contenders=_rank(title_rows, value_key="title_points", require_positive=True),
            ),
            *base_title_races,
        ]
        victory_rule = (
            "Season Champion is the qualified title-points leader across Lawwright, Refuter, "
            "Frontier Explorer, Territory, Compression, Characterizer, and Clean Play. "
            "Race ranks score 5/3/1 title points; raw score breaks ties."
        )
    else:
        title_races = [
            _race(
                key="championship",
                title="Season Champion",
                description="Highest total score at the scheduled move cap.",
                contenders=_rank(title_rows, value_key="total"),
            ),
            *base_title_races,
        ]
        victory_rule = (
            f"Season Champion is the qualified total-score leader after {move_cap} public moves. "
            "Secondary titles keep different strategies live even when the main race separates."
        )
    display_season_id = season.spec.season_id if season else season_id()
    return SeasonStandings(
        season_id=display_season_id,
        total_moves=total_moves,
        move_cap=move_cap,
        moves_remaining=moves_remaining,
        phase=_phase(total_moves, move_cap, frontier.coverage_ratio, coverage_target_ratio),
        season_complete=moves_remaining == 0,
        coverage_target_ratio=coverage_target_ratio,
        coverage_target_met=coverage_target_met,
        victory_rule=victory_rule,
        leaderboard=enriched_rows,
        qualified_players=sorted(qualified_players),
        unqualified_players=sorted(row["player"] for row in enriched_rows if row["player"] not in qualified_players),
        title_races=title_races,
        frontier={
            "covered_obligations": frontier.covered_obligations,
            "uncovered_obligations": frontier.uncovered_obligations,
            "total_obligations": frontier.total_obligations,
            "coverage_ratio": frontier.coverage_ratio,
            "open_frontier": frontier.open_frontier[:5],
            "stale_traps": frontier.stale_traps[:5],
        },
        next_objectives=_next_objectives(
            frontier,
            enriched_rows,
            victory_metric="title_points" if _uses_title_points(season) else "total",
        ),
    )


def render_standings_markdown(standings: SeasonStandings) -> str:
    data = standings.to_dict()
    lines = [
        "# Season Standings",
        "",
        f"Season: `{data['season_id']}`",
        f"Phase: `{data['phase']}`",
        f"Victory rule: {data['victory_rule']}",
        "",
        "| status | value |",
        "| --- | ---: |",
        f"| moves played | {data['total_moves']} |",
        f"| move cap | {data['move_cap']} |",
        f"| moves remaining | {data['moves_remaining']} |",
        f"| coverage ratio | {data['frontier']['coverage_ratio']:.6f} |",
        f"| coverage target | {data['coverage_target_ratio']:.2f} |",
        f"| coverage target met | {str(data['coverage_target_met']).lower()} |",
        f"| season complete | {str(data['season_complete']).lower()} |",
        f"| qualified players | {len(data['qualified_players'])} |",
        f"| unqualified players | {len(data['unqualified_players'])} |",
        "",
        "## Leaderboard",
        "",
        render_markdown(data["leaderboard"]),
        "",
        "## Title Races",
        "",
        "| title | leader | value | rule |",
        "| --- | --- | ---: | --- |",
    ]
    for race in data["title_races"]:
        leader = race["leader"] or "-"
        value = race["value"] if race["value"] is not None else "-"
        lines.append(f"| {race['title']} | `{leader}` | {value} | {race['description']} |")
    if data["unqualified_players"]:
        lines.extend(["", "## Unqualified Players", ""])
        lines.append("Players need at least one valid conjecture or valid counterexample to enter title races.")
        lines.append("")
        for player in data["unqualified_players"]:
            lines.append(f"- `{player}`")
    lines.extend(["", "## Next Objectives", ""])
    for objective in data["next_objectives"]:
        lines.append(f"- {objective}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render deterministic Conjecture Golf season standings.")
    parser.add_argument("path", help="JSONL transcript path")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    parser.add_argument(
        "--min-player-interval-seconds",
        type=int,
        default=0,
        help="Apply the same cooldown rule used by replay.",
    )
    parser.add_argument("--no-season-scoring", action="store_true", help="Replay without season scoring.")
    parser.add_argument("--season", help="Optional data-only season spec path")
    parser.add_argument("--move-cap", type=int, default=DEFAULT_MOVE_CAP, help="Scheduled public move cap.")
    parser.add_argument(
        "--coverage-target-ratio",
        type=float,
        default=DEFAULT_COVERAGE_TARGET_RATIO,
        help="Public coverage target used for phase and status diagnostics.",
    )
    args = parser.parse_args(argv)
    season = load_optional_compiled_season(args.season)
    standings = build_season_standings(
        iter_jsonl(args.path),
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=not args.no_season_scoring,
        season=season,
        move_cap=args.move_cap,
        coverage_target_ratio=args.coverage_target_ratio,
    )
    if args.json:
        print(json.dumps(standings.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_standings_markdown(standings))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
