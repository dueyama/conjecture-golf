"""Verification CLI and library for Conjecture Golf."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from .dsl import complexity, evaluate_on_board, player_name_from_submission, validate_conjecture
from .world import BOARD_SIZE, Board, ValidationError, canonical_test_boards, evolve, format_board, related_coords, tiny_local_boards, validate_board


@dataclass(frozen=True)
class Verdict:
    ok: bool
    kind: str
    message: str
    player: str = "anonymous"
    score_delta: int = 0
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _center_embed_3x3(local: Sequence[str]) -> Board:
    """Embed a 3x3 local board into the middle of a 5x5 empty board."""

    if len(local) != 3 or any(len(row) != 3 for row in local):
        raise ValidationError("local board must be 3x3")
    board = [list(".....") for _ in range(BOARD_SIZE)]
    for r in range(3):
        for c in range(3):
            ch = local[r][c]
            if ch not in {".", "F", "W", "S"}:
                raise ValidationError("local board contains invalid symbols")
            board[r + 1][c + 1] = ch
    return ["".join(row) for row in board]




def _condition_matches_fast(condition: dict[str, Any], board: Sequence[str], row: int, col: int) -> bool:
    """Fast condition check for already-normalized conjectures and boards."""

    key = next(iter(condition))
    value = condition[key]
    if key == "target_is":
        return board[row][col] == value

    counts = {".": 0, "F": 0, "W": 0, "S": 0}
    for rr, cc in related_coords(row, col, value["relation"], size=len(board)):
        counts[board[rr][cc]] += 1

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


def _antecedent_matches_fast(conjecture: Mapping[str, Any], board: Sequence[str], row: int, col: int) -> bool:
    return all(_condition_matches_fast(condition, board, row, col) for condition in conjecture["if"])



def _relation_count_fast(board: Sequence[str], row: int, col: int, relation: str) -> dict[str, int]:
    counts = {".": 0, "F": 0, "W": 0, "S": 0}
    for rr, cc in related_coords(row, col, relation, size=len(board)):
        counts[board[rr][cc]] += 1
    return counts


def _evolve_cell_fast(board: Sequence[str], row: int, col: int) -> str:
    target = board[row][col]
    orth = _relation_count_fast(board, row, col, "orthogonal")
    diag = _relation_count_fast(board, row, col, "diagonal")
    king = _relation_count_fast(board, row, col, "king")
    if target == "." and diag["W"] >= 1 and orth["F"] >= 1 and king["S"] == 0:
        return "F"
    if target == "F" and king["S"] >= 2:
        return "."
    if target == "." and orth["W"] == 2 and diag["S"] == 0:
        return "W"
    if target == "W" and orth["."] == 0:
        return "."
    return target


def verify_conjecture(conjecture: Mapping[str, Any], *, exhaustive_local: bool = True) -> Verdict:
    """Verify whether a conjecture is true for the public world rule.

    The MVP checks all possible 3x3 neighborhoods around the center cell by
    embedding them into a 5x5 board. Because the public evolution rule is local,
    this is a meaningful and deterministic check for the center cell.
    """

    try:
        normalized = validate_conjecture(conjecture)
        player = player_name_from_submission(normalized)
        obligations_checked = 0
        counterexamples: list[dict[str, Any]] = []

        expected = normalized["then"]["target_becomes"]
        if exhaustive_local:
            # Check the center cell for every possible 3x3 local neighborhood.
            # This is fast enough and avoids full-board repeated validation.
            for local in tiny_local_boards(size=3):
                board = _center_embed_3x3(local)
                row, col = 2, 2
                if not _antecedent_matches_fast(normalized, board, row, col):
                    continue
                obligations_checked += 1
                actual = _evolve_cell_fast(board, row, col)
                if actual != expected:
                    counterexamples.append(
                        {
                            "board": board,
                            "after": evolve(board),
                            "cell": [row, col],
                            "expected": expected,
                            "actual": actual,
                        }
                    )
                    break
        else:
            for board in canonical_test_boards():
                for row in range(BOARD_SIZE):
                    for col in range(BOARD_SIZE):
                        if not _antecedent_matches_fast(normalized, board, row, col):
                            continue
                        obligations_checked += 1
                        actual = _evolve_cell_fast(board, row, col)
                        if actual != expected:
                            counterexamples.append(
                                {
                                    "board": board,
                                    "after": evolve(board),
                                    "cell": [row, col],
                                    "expected": expected,
                                    "actual": actual,
                                }
                            )
                            break
                    if counterexamples:
                        break
                if counterexamples:
                    break

        comp = complexity(normalized)
        if counterexamples:
            return Verdict(
                ok=False,
                kind="conjecture",
                player=player,
                message=f"Conjecture {normalized['name']!r} is false; a counterexample was found.",
                score_delta=-5,
                details={
                    "name": normalized["name"],
                    "complexity": comp,
                    "obligations_checked_before_failure": obligations_checked,
                    "counterexample": counterexamples[0],
                },
            )

        # Reward non-vacuous, short conjectures. Empty coverage is not useful.
        if obligations_checked == 0:
            return Verdict(
                ok=False,
                kind="conjecture",
                player=player,
                message=f"Conjecture {normalized['name']!r} is vacuous on the exhaustive local check.",
                score_delta=-5,
                details={"name": normalized["name"], "complexity": comp, "coverage": 0},
            )

        coverage_bonus = min(40, obligations_checked // 512)
        score_delta = max(1, 10 + coverage_bonus - comp)
        return Verdict(
            ok=True,
            kind="conjecture",
            player=player,
            message=f"Conjecture {normalized['name']!r} holds on the exhaustive local check.",
            score_delta=score_delta,
            details={
                "name": normalized["name"],
                "complexity": comp,
                "coverage": obligations_checked,
                "coverage_bonus": coverage_bonus,
            },
        )
    except ValidationError as exc:
        return Verdict(ok=False, kind="conjecture", message=str(exc), score_delta=-5)


def check_counterexample(conjecture: Mapping[str, Any], before: Sequence[str]) -> Verdict:
    """Check whether a board is a valid counterexample to a conjecture.

    The supplied board is the before-state. The verifier computes the after-state
    using the public world rule. A counterexample is valid when some target cell
    satisfies the conjecture's antecedent but evolves to a symbol different from
    the conjecture's consequent.
    """

    try:
        normalized = validate_conjecture(conjecture)
        board = validate_board(list(before))
        obligations = evaluate_on_board(normalized, board)
        failures = [item for item in obligations if not item["holds"]]
        player = player_name_from_submission(normalized)
        if not failures:
            return Verdict(
                ok=False,
                kind="counterexample",
                player=player,
                message="The board is not a counterexample; every triggered obligation holds.",
                score_delta=-5,
                details={"obligations": len(obligations), "before": board, "after": evolve(board)},
            )
        first = failures[0]
        occupied = sum(ch != "." for row in board for ch in row)
        minimality_bonus = max(0, 15 - occupied)
        score_delta = 20 + minimality_bonus
        return Verdict(
            ok=True,
            kind="counterexample",
            player=player,
            message=f"Valid counterexample against {normalized['name']!r} at cell ({first['row']}, {first['col']}).",
            score_delta=score_delta,
            details={
                "name": normalized["name"],
                "before": board,
                "after": evolve(board),
                "cell": [first["row"], first["col"]],
                "expected": first["expected"],
                "actual": first["actual"],
                "minimality_bonus": minimality_bonus,
            },
        )
    except ValidationError as exc:
        return Verdict(ok=False, kind="counterexample", message=str(exc), score_delta=-5)


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def verify_file(path: str | Path) -> Verdict:
    payload = load_json(path)
    if not isinstance(payload, dict):
        return Verdict(ok=False, kind="file", message="top-level JSON must be an object", score_delta=-5)
    if payload.get("type") == "counterexample":
        conjecture = payload.get("conjecture")
        before = payload.get("before") or payload.get("board")
        if conjecture is None or before is None:
            return Verdict(ok=False, kind="counterexample", message="counterexample file needs conjecture and before/board", score_delta=-5)
        return check_counterexample(conjecture, before)
    if payload.get("type") == "conjecture":
        payload = {k: v for k, v in payload.items() if k != "type"}
    return verify_conjecture(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a Conjecture Golf JSON file.")
    parser.add_argument("path", help="Path to a conjecture or counterexample JSON file")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON verdict")
    args = parser.parse_args(argv)
    verdict = verify_file(args.path)
    indent = 2 if args.pretty else None
    print(json.dumps(verdict.to_dict(), ensure_ascii=False, indent=indent))
    return 0 if verdict.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
