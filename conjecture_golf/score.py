"""Score aggregation for Conjecture Golf."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .verify import Verdict


@dataclass
class PlayerScore:
    player: str
    total: int = 0
    law_score: int = 0
    counterexample_score: int = 0
    invalid_penalty: int = 0
    other_score: int = 0
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
        ps.law_score += verdict.score_delta
        ps.valid_conjectures += 1
        details = verdict.details or {}
        if "complexity" in details:
            ps.conjecture_complexities.append(int(details["complexity"]))
    elif verdict.ok and verdict.kind == "counterexample":
        ps.counterexample_score += verdict.score_delta
        ps.valid_counterexamples += 1
    elif not verdict.ok:
        ps.invalid_penalty += verdict.score_delta
        ps.invalid_moves += 1
    else:
        ps.other_score += verdict.score_delta


def leaderboard_rows(scores: dict[str, PlayerScore]) -> list[dict[str, Any]]:
    rows = []
    for player, ps in scores.items():
        rows.append(
            {
                "player": player,
                "total": ps.total,
                "law_score": ps.law_score,
                "counterexample_score": ps.counterexample_score,
                "invalid_penalty": ps.invalid_penalty,
                "other_score": ps.other_score,
                "valid_conjectures": ps.valid_conjectures,
                "valid_counterexamples": ps.valid_counterexamples,
                "invalid_moves": ps.invalid_moves,
                "avg_complexity": round(ps.average_conjecture_complexity, 2),
            }
        )
    return sorted(rows, key=lambda row: (-row["total"], row["player"]))


def render_markdown(rows: Iterable[dict[str, Any]]) -> str:
    lines = [
        "| rank | player | total | laws | counterexamples | invalid penalty | conjectures | refutations | invalid | avg complexity |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for idx, row in enumerate(rows, start=1):
        lines.append(
            f"| {idx} | {row['player']} | {row['total']} | {row['law_score']} | "
            f"{row['counterexample_score']} | {row['invalid_penalty']} | "
            f"{row['valid_conjectures']} | {row['valid_counterexamples']} | "
            f"{row['invalid_moves']} | {row['avg_complexity']} |"
        )
    return "\n".join(lines)
