"""Score aggregation for Conjecture Golf."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .verify import Verdict


@dataclass
class PlayerScore:
    player: str
    total: int = 0
    valid_conjectures: int = 0
    valid_counterexamples: int = 0
    invalid_moves: int = 0
    conjecture_complexities: list[int] = field(default_factory=list)

    @property
    def average_conjecture_complexity(self) -> float:
        if not self.conjecture_complexities:
            return 0.0
        return sum(self.conjecture_complexities) / len(self.conjecture_complexities)


def apply_verdict(scores: dict[str, PlayerScore], verdict: Verdict) -> None:
    player = verdict.player or "anonymous"
    if player not in scores:
        scores[player] = PlayerScore(player=player)
    ps = scores[player]
    ps.total += verdict.score_delta
    if verdict.ok and verdict.kind == "conjecture":
        ps.valid_conjectures += 1
        details = verdict.details or {}
        if "complexity" in details:
            ps.conjecture_complexities.append(int(details["complexity"]))
    elif verdict.ok and verdict.kind == "counterexample":
        ps.valid_counterexamples += 1
    elif not verdict.ok:
        ps.invalid_moves += 1


def leaderboard_rows(scores: dict[str, PlayerScore]) -> list[dict[str, Any]]:
    rows = []
    for player, ps in scores.items():
        rows.append(
            {
                "player": player,
                "total": ps.total,
                "valid_conjectures": ps.valid_conjectures,
                "valid_counterexamples": ps.valid_counterexamples,
                "invalid_moves": ps.invalid_moves,
                "avg_complexity": round(ps.average_conjecture_complexity, 2),
            }
        )
    return sorted(rows, key=lambda row: (-row["total"], row["player"]))


def render_markdown(rows: Iterable[dict[str, Any]]) -> str:
    lines = [
        "| rank | player | score | conjectures | counterexamples | invalid | avg complexity |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.append(
            f"| {idx} | {row['player']} | {row['total']} | {row['valid_conjectures']} | "
            f"{row['valid_counterexamples']} | {row['invalid_moves']} | {row['avg_complexity']} |"
        )
    return "\n".join(lines)
