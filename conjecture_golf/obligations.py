"""Season obligation ledger for Conjecture Golf.

An obligation is a deterministic local fact covered by an accepted claim. Season
scoring uses obligation IDs to reward new territory and discount stale claims.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .dsl import validate_conjecture
from .world import BOARD_SIZE, Board, ValidationError, related_coords, tiny_local_boards

WORLD_VERSION = "season_0"
CLAIM_KIND_SUFFICIENT = "sufficient"


@dataclass(frozen=True)
class Coverage:
    obligations: frozenset[str]
    new_obligations: frozenset[str]
    stale_obligations: frozenset[str]


@dataclass
class ObligationLedger:
    covered: set[str] = field(default_factory=set)

    def measure(self, obligations: set[str] | frozenset[str]) -> Coverage:
        all_obligations = frozenset(obligations)
        stale = frozenset(item for item in all_obligations if item in self.covered)
        new = all_obligations - stale
        return Coverage(obligations=all_obligations, new_obligations=new, stale_obligations=stale)

    def mark(self, coverage: Coverage) -> None:
        self.covered.update(coverage.obligations)


def _center_embed_3x3(local: Sequence[str]) -> Board:
    if len(local) != 3 or any(len(row) != 3 for row in local):
        raise ValidationError("local board must be 3x3")
    board = [list(".....") for _ in range(BOARD_SIZE)]
    for row in range(3):
        for col in range(3):
            board[row + 1][col + 1] = local[row][col]
    return ["".join(row) for row in board]


def _relation_counts(board: Sequence[str], row: int, col: int, relation: str) -> dict[str, int]:
    counts = {".": 0, "F": 0, "W": 0, "S": 0}
    for rr, cc in related_coords(row, col, relation, size=len(board)):
        counts[board[rr][cc]] += 1
    return counts


def _condition_matches(condition: Mapping[str, Any], board: Sequence[str], row: int, col: int) -> bool:
    key = next(iter(condition))
    value = condition[key]
    if key == "target_is":
        return board[row][col] == value

    counts = _relation_counts(board, row, col, value["relation"])
    symbol = value["symbol"]
    if key == "exists":
        return counts[symbol] >= 1
    if key == "not_exists":
        return counts[symbol] == 0
    if key == "count_at_least":
        return counts[symbol] >= value["n"]
    if key == "count_exactly":
        return counts[symbol] == value["n"]
    raise ValidationError(f"unknown condition kind: {key}")


def _antecedent_matches(conjecture: Mapping[str, Any], board: Sequence[str], row: int, col: int) -> bool:
    return all(_condition_matches(condition, board, row, col) for condition in conjecture["if"])


def _evolve_cell_fast(board: Sequence[str], row: int, col: int) -> str:
    target = board[row][col]
    orth = _relation_counts(board, row, col, "orthogonal")
    diag = _relation_counts(board, row, col, "diagonal")
    king = _relation_counts(board, row, col, "king")
    if target == "." and diag["W"] >= 1 and orth["F"] >= 1 and king["S"] == 0:
        return "F"
    if target == "F" and king["S"] >= 2:
        return "."
    if target == "." and orth["W"] == 2 and diag["S"] == 0:
        return "W"
    if target == "W" and orth["."] == 0:
        return "."
    return target


def obligation_id(
    *,
    world_version: str,
    center_before_symbol: str,
    center_after_symbol: str,
    local_neighborhood_index: int,
    claim_kind: str,
) -> str:
    return (
        f"{world_version}:claim={claim_kind}:before={center_before_symbol}:"
        f"after={center_after_symbol}:local={local_neighborhood_index:06d}"
    )


def obligation_ids_for_conjecture(
    conjecture: Mapping[str, Any],
    *,
    world_version: str = WORLD_VERSION,
) -> frozenset[str]:
    normalized = validate_conjecture(conjecture)
    claim_kind = str(normalized.get("claim_kind", CLAIM_KIND_SUFFICIENT))
    expected = normalized["then"]["target_becomes"]
    obligations: set[str] = set()
    for index, local in enumerate(tiny_local_boards(size=3)):
        board = _center_embed_3x3(local)
        antecedent = _antecedent_matches(normalized, board, 2, 2)
        actual = _evolve_cell_fast(board, 2, 2)
        target_produced = actual == expected
        if claim_kind in {"sufficient", "equivalence"} and antecedent:
            obligations.add(
                obligation_id(
                    world_version=world_version,
                    center_before_symbol=board[2][2],
                    center_after_symbol=expected,
                    local_neighborhood_index=index,
                    claim_kind=CLAIM_KIND_SUFFICIENT,
                )
            )
        if claim_kind in {"necessary", "equivalence"} and target_produced:
            obligations.add(
                obligation_id(
                    world_version=world_version,
                    center_before_symbol=board[2][2],
                    center_after_symbol=expected,
                    local_neighborhood_index=index,
                    claim_kind="necessary",
                )
            )
    return frozenset(obligations)
