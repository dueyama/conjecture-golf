"""Deterministic Season 0 transcript evaluation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .frontier import build_frontier_report
from .replay import ReplayState, iter_jsonl, replay_records
from .score import leaderboard_rows
from .season_catalog import load_optional_compiled_season
from .season_engine import CompiledSeason
from .season import season_id


@dataclass(frozen=True)
class SeasonEvaluation:
    season_id: str
    total_moves: int
    valid_conjectures: int
    valid_counterexamples: int
    invalid_moves: int
    stale_moves: int
    duplicate_moves: int
    players: list[str]
    score_spread: int
    final_leader: dict[str, Any] | None
    frontier_remaining: dict[str, Any]
    best_law: dict[str, Any] | None
    best_counterexample: dict[str, Any] | None
    strategic_styles: list[str]
    style_notes_by_player: dict[str, list[str]]
    has_two_distinct_strategic_styles: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "season_id": self.season_id,
            "total_moves": self.total_moves,
            "valid_conjectures": self.valid_conjectures,
            "valid_counterexamples": self.valid_counterexamples,
            "invalid_moves": self.invalid_moves,
            "stale_moves": self.stale_moves,
            "duplicate_moves": self.duplicate_moves,
            "players": self.players,
            "score_spread": self.score_spread,
            "final_leader": self.final_leader,
            "frontier_remaining": self.frontier_remaining,
            "best_law": self.best_law,
            "best_counterexample": self.best_counterexample,
            "strategic_styles": self.strategic_styles,
            "style_notes_by_player": self.style_notes_by_player,
            "has_two_distinct_strategic_styles": self.has_two_distinct_strategic_styles,
        }


def _verdict_name(verdict: Any) -> str:
    details = verdict.details or {}
    name = details.get("name")
    if isinstance(name, str) and name:
        return name
    return str(verdict.kind)


def _law_summary(verdict: Any) -> dict[str, Any]:
    details = verdict.details or {}
    return {
        "name": _verdict_name(verdict),
        "player": verdict.player,
        "score_delta": verdict.score_delta,
        "claim_kind": details.get("claim_kind", "sufficient"),
        "new_obligations": details.get("season_new_obligations"),
    }


def _counterexample_summary(verdict: Any) -> dict[str, Any]:
    details = verdict.details or {}
    return {
        "player": verdict.player,
        "score_delta": verdict.score_delta,
        "against": details.get("against"),
        "minimality_bonus": details.get("minimality_bonus", 0),
        "score_basis": details.get("season_score_basis"),
    }


def _strategic_styles(verdicts: Iterable[Any]) -> list[str]:
    styles: set[str] = set()
    for verdict in verdicts:
        details = verdict.details or {}
        if verdict.kind == "conjecture" and verdict.ok:
            claim_kind = details.get("claim_kind", "sufficient")
            if claim_kind == "equivalence":
                styles.add("equivalence_characterization")
            elif claim_kind == "necessary":
                styles.add("necessary_condition")
            else:
                styles.add("sufficient_law")
        if verdict.kind == "conjecture" and not verdict.ok:
            styles.add("risky_generalization")
        if verdict.kind == "counterexample" and verdict.ok:
            styles.add("counterexample_hunting")
        if details.get("season_score_basis") in {"stale_true_conjecture", "duplicate_conjecture", "duplicate_witness"}:
            styles.add("stale_or_duplicate_pressure")
    return sorted(styles)


def style_notes_by_player(verdicts: Iterable[Any]) -> dict[str, list[str]]:
    stats: dict[str, dict[str, int]] = {}
    for verdict in verdicts:
        player = verdict.player or "anonymous"
        details = verdict.details or {}
        player_stats = stats.setdefault(
            player,
            {
                "accepted_laws": 0,
                "necessary_or_equivalence": 0,
                "new_obligations": 0,
                "valid_counterexamples": 0,
                "novel_counterexamples": 0,
                "false_conjectures": 0,
                "stale_or_duplicate": 0,
                "invalid": 0,
            },
        )
        basis = details.get("season_score_basis")
        if verdict.kind == "conjecture" and verdict.ok:
            player_stats["accepted_laws"] += 1
            player_stats["new_obligations"] += int(details.get("season_new_obligations") or 0)
            if details.get("claim_kind") in {"necessary", "equivalence"}:
                player_stats["necessary_or_equivalence"] += 1
        elif verdict.kind == "conjecture":
            player_stats["false_conjectures"] += 1
        if verdict.kind == "counterexample" and verdict.ok:
            player_stats["valid_counterexamples"] += 1
            if basis == "novel_first_counterexample":
                player_stats["novel_counterexamples"] += 1
        if verdict.kind == "invalid":
            player_stats["invalid"] += 1
        if basis in {"stale_true_conjecture", "already_countered", "duplicate_witness", "duplicate_conjecture"}:
            player_stats["stale_or_duplicate"] += 1
        if details.get("reason") == "duplicate_conjecture":
            player_stats["stale_or_duplicate"] += 1

    notes_by_player: dict[str, list[str]] = {}
    for player in sorted(stats):
        player_stats = stats[player]
        notes: list[str] = []
        if player_stats["new_obligations"] > 0:
            notes.append(f"frontier opener: covered {player_stats['new_obligations']} new obligations")
        if player_stats["necessary_or_equivalence"] > 0:
            notes.append(
                "characterizer: used "
                f"{player_stats['necessary_or_equivalence']} necessary/equivalence claim(s)"
            )
        if player_stats["novel_counterexamples"] > 0:
            notes.append(
                "original refuter: found "
                f"{player_stats['novel_counterexamples']} novel first counterexample(s)"
            )
        elif player_stats["valid_counterexamples"] > 0:
            notes.append(f"refuter: found {player_stats['valid_counterexamples']} valid counterexample(s)")
        if player_stats["false_conjectures"] > 0:
            notes.append(f"aggressive generalizer: submitted {player_stats['false_conjectures']} refuted conjecture(s)")
        if player_stats["stale_or_duplicate"] > 0:
            notes.append(f"stale pressure: {player_stats['stale_or_duplicate']} stale or duplicate move(s)")
        if player_stats["invalid"] > 0:
            notes.append(f"protocol risk: {player_stats['invalid']} invalid move(s)")
        if not notes:
            notes.append("no scoring style detected yet")
        notes_by_player[player] = notes
    return notes_by_player


def evaluate_records(
    records: Iterable[Mapping[str, Any]],
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
    season: CompiledSeason | None = None,
) -> SeasonEvaluation:
    state = replay_records(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )
    return evaluate_state(state, season=season)


def evaluate_state(
    state: ReplayState,
    *,
    season: CompiledSeason | None = None,
) -> SeasonEvaluation:
    verdicts = state.verdicts
    rows = leaderboard_rows(state.scores)
    accepted_laws = [v for v in verdicts if v.kind == "conjecture" and v.ok]
    accepted_non_equivalence = [
        v for v in accepted_laws if (v.details or {}).get("claim_kind", "sufficient") != "equivalence"
    ]
    accepted_counterexamples = [v for v in verdicts if v.kind == "counterexample" and v.ok]
    score_values = [int(row["total"]) for row in rows]
    frontier = build_frontier_report(state, season=season)
    styles = _strategic_styles(verdicts)
    style_notes = style_notes_by_player(verdicts)

    return SeasonEvaluation(
        season_id=season.spec.season_id if season else season_id(),
        total_moves=len(verdicts),
        valid_conjectures=len(accepted_laws),
        valid_counterexamples=len(accepted_counterexamples),
        invalid_moves=sum(1 for v in verdicts if not v.ok),
        stale_moves=sum(
            1
            for v in verdicts
            if (v.details or {}).get("season_score_basis") in {"stale_true_conjecture", "already_countered"}
        ),
        duplicate_moves=sum(
            1
            for v in verdicts
            if (v.details or {}).get("reason") == "duplicate_conjecture"
            or (v.details or {}).get("season_score_basis") == "duplicate_witness"
        ),
        players=sorted(state.scores),
        score_spread=max(score_values) - min(score_values) if score_values else 0,
        final_leader=rows[0] if rows else None,
        frontier_remaining={
            "uncovered_obligations": frontier.uncovered_obligations,
            "coverage_ratio": frontier.coverage_ratio,
            "top_open": frontier.open_frontier[:3],
        },
        best_law=_law_summary(
            max(
                accepted_non_equivalence,
                key=lambda v: (v.score_delta, (v.details or {}).get("season_new_obligations", 0)),
            )
        )
        if accepted_non_equivalence
        else None,
        best_counterexample=_counterexample_summary(
            max(
                accepted_counterexamples,
                key=lambda v: (v.score_delta, (v.details or {}).get("minimality_bonus", 0)),
            )
        )
        if accepted_counterexamples
        else None,
        strategic_styles=styles,
        style_notes_by_player=style_notes,
        has_two_distinct_strategic_styles=len(styles) >= 2,
    )


def render_evaluation_markdown(evaluation: SeasonEvaluation) -> str:
    data = evaluation.to_dict()
    lines = [
        "# Season Evaluation",
        "",
        f"Season: `{data['season_id']}`",
        "",
        "| metric | value |",
        "| --- | ---: |",
        f"| total moves | {data['total_moves']} |",
        f"| valid conjectures | {data['valid_conjectures']} |",
        f"| valid counterexamples | {data['valid_counterexamples']} |",
        f"| invalid moves | {data['invalid_moves']} |",
        f"| stale moves | {data['stale_moves']} |",
        f"| duplicate moves | {data['duplicate_moves']} |",
        f"| players | {len(data['players'])} |",
        f"| score spread | {data['score_spread']} |",
        f"| frontier remaining | {data['frontier_remaining']['uncovered_obligations']} |",
        "",
    ]
    leader = data["final_leader"]
    lines.append(
        f"Final leader: `{leader['player']}` with `{leader['total']}` points."
        if leader
        else "Final leader: none."
    )
    best_law = data["best_law"]
    lines.append(
        f"Best law: `{best_law['name']}` by `{best_law['player']}` for `{best_law['score_delta']}` points."
        if best_law
        else "Best law: none."
    )
    best_counterexample = data["best_counterexample"]
    lines.append(
        "Best counterexample: "
        f"`{best_counterexample['player']}` against `{best_counterexample['against']}` "
        f"for `{best_counterexample['score_delta']}` points."
        if best_counterexample
        else "Best counterexample: none."
    )
    lines.extend(["", "## Frontier Remaining", "", "| claim_kind | transition | uncovered |", "| --- | --- | ---: |"])
    for row in data["frontier_remaining"]["top_open"]:
        lines.append(f"| {row['claim_kind']} | {row['transition']} | {row['count']} |")
    if not data["frontier_remaining"]["top_open"]:
        lines.append("| - | - | 0 |")
    lines.extend(["", "## Strategic Styles", ""])
    if data["strategic_styles"]:
        lines.extend(f"- `{style}`" for style in data["strategic_styles"])
    else:
        lines.append("- none detected")
    lines.extend(["", "## Player Style Notes", ""])
    if data["style_notes_by_player"]:
        for player, notes in data["style_notes_by_player"].items():
            lines.append(f"- `{player}`: {'; '.join(notes)}.")
    else:
        lines.append("- none detected")
    lines.append("")
    lines.append(
        "Two or more distinct strategic styles: "
        f"`{str(data['has_two_distinct_strategic_styles']).lower()}`."
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a Season 0 transcript deterministically.")
    parser.add_argument("path", help="JSONL transcript path")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    parser.add_argument(
        "--min-player-interval-seconds",
        type=int,
        default=0,
        help="Apply the same cooldown rule used by replay.",
    )
    parser.add_argument("--no-season-scoring", action="store_true", help="Evaluate without season scoring.")
    parser.add_argument("--season", help="Optional data-only season spec path")
    args = parser.parse_args(argv)
    season = load_optional_compiled_season(args.season)
    evaluation = evaluate_records(
        iter_jsonl(args.path),
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=not args.no_season_scoring,
        season=season,
    )
    if args.json:
        print(json.dumps(evaluation.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_evaluation_markdown(evaluation))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
