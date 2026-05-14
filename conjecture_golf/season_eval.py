"""Deterministic Season 0 transcript evaluation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .frontier import build_frontier_report
from .replay import iter_jsonl, replay_records
from .score import leaderboard_rows
from .season import season_id


@dataclass(frozen=True)
class SeasonEvaluation:
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
    has_two_distinct_strategic_styles: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "season_id": season_id(),
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


def evaluate_records(
    records: Iterable[Mapping[str, Any]],
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
) -> SeasonEvaluation:
    state = replay_records(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
    )
    verdicts = state.verdicts
    rows = leaderboard_rows(state.scores)
    accepted_laws = [v for v in verdicts if v.kind == "conjecture" and v.ok]
    accepted_non_equivalence = [
        v for v in accepted_laws if (v.details or {}).get("claim_kind", "sufficient") != "equivalence"
    ]
    accepted_counterexamples = [v for v in verdicts if v.kind == "counterexample" and v.ok]
    score_values = [int(row["total"]) for row in rows]
    frontier = build_frontier_report(state)
    styles = _strategic_styles(verdicts)

    return SeasonEvaluation(
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
    args = parser.parse_args(argv)
    evaluation = evaluate_records(
        iter_jsonl(args.path),
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=not args.no_season_scoring,
    )
    if args.json:
        print(json.dumps(evaluation.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_evaluation_markdown(evaluation))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
