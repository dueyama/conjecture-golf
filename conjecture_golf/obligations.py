"""Season obligation ledger for Conjecture Golf.

An obligation is a deterministic local fact covered by an accepted claim. Season
scoring uses obligation IDs to reward new territory and discount stale claims.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from .dsl import validate_conjecture
from .world import BOARD_SIZE, Board, ValidationError, related_coords, tiny_local_boards

WORLD_VERSION = "season_0"
CLAIM_KIND_SUFFICIENT = "sufficient"
CLAIM_KIND_NECESSARY = "necessary"
CLAIM_KINDS = (CLAIM_KIND_SUFFICIENT, CLAIM_KIND_NECESSARY)


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


def parse_obligation_id(identifier: str) -> dict[str, Any]:
    parts = identifier.split(":")
    if len(parts) != 5:
        raise ValidationError("obligation ID must have five colon-separated parts")
    parsed: dict[str, Any] = {"world_version": parts[0]}
    for part in parts[1:]:
        if "=" not in part:
            raise ValidationError("obligation ID part must be key=value")
        key, value = part.split("=", 1)
        parsed[key] = value
    if parsed.get("claim") not in set(CLAIM_KINDS):
        raise ValidationError("obligation ID has unknown claim kind")
    before = parsed.get("before")
    after = parsed.get("after")
    if before not in {".", "F", "W", "S"} or after not in {".", "F", "W", "S"}:
        raise ValidationError("obligation ID has unknown symbol")
    try:
        parsed["local_index"] = int(str(parsed["local"]))
    except (KeyError, ValueError) as exc:
        raise ValidationError("obligation ID has invalid local index") from exc
    return parsed


@lru_cache(maxsize=1)
def all_local_obligation_ids(*, world_version: str = WORLD_VERSION) -> frozenset[str]:
    obligations: set[str] = set()
    for index, local in enumerate(tiny_local_boards(size=3)):
        board = _center_embed_3x3(local)
        actual = _evolve_cell_fast(board, 2, 2)
        before = board[2][2]
        for claim_kind in CLAIM_KINDS:
            obligations.add(
                obligation_id(
                    world_version=world_version,
                    center_before_symbol=before,
                    center_after_symbol=actual,
                    local_neighborhood_index=index,
                    claim_kind=claim_kind,
                )
            )
    return frozenset(obligations)


def summarize_obligation_ids(obligations: Iterable[str]) -> dict[str, Any]:
    by_claim_kind = {claim_kind: 0 for claim_kind in CLAIM_KINDS}
    by_transition: dict[str, int] = {}
    by_claim_and_transition: dict[str, int] = {}
    total = 0
    for obligation in obligations:
        parsed = parse_obligation_id(obligation)
        claim_kind = str(parsed["claim"])
        transition = f"{parsed['before']}->{parsed['after']}"
        by_claim_kind[claim_kind] = by_claim_kind.get(claim_kind, 0) + 1
        by_transition[transition] = by_transition.get(transition, 0) + 1
        key = f"{claim_kind}:{transition}"
        by_claim_and_transition[key] = by_claim_and_transition.get(key, 0) + 1
        total += 1
    return {
        "total": total,
        "by_claim_kind": by_claim_kind,
        "by_transition": dict(sorted(by_transition.items())),
        "by_claim_and_transition": dict(sorted(by_claim_and_transition.items())),
    }


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
                    claim_kind=CLAIM_KIND_NECESSARY,
                )
            )
    return frozenset(obligations)
