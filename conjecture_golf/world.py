"""Tiny deterministic symbolic world used by Conjecture Golf.

The world is public and deterministic. There is no hidden judge.
A move, conjecture, or counterexample can be verified by anyone locally.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import product
from typing import Iterable, Iterator, Sequence

BOARD_SIZE = 5
SYMBOLS = {".", "F", "W", "S"}
RELATIONS = {"orthogonal", "diagonal", "king"}

Board = list[str]
Coord = tuple[int, int]  # (row, col)

ORTHOGONAL_OFFSETS: tuple[Coord, ...] = ((-1, 0), (1, 0), (0, -1), (0, 1))
DIAGONAL_OFFSETS: tuple[Coord, ...] = ((-1, -1), (-1, 1), (1, -1), (1, 1))
KING_OFFSETS: tuple[Coord, ...] = ORTHOGONAL_OFFSETS + DIAGONAL_OFFSETS


class ValidationError(ValueError):
    """Raised when a board, conjecture, or command is malformed."""


@dataclass(frozen=True)
class LocalStats:
    """A compact description of a target cell's local neighborhood."""

    target: str
    orthogonal: Counter[str]
    diagonal: Counter[str]
    king: Counter[str]


def validate_board(board: Sequence[str], *, size: int = BOARD_SIZE) -> Board:
    """Return a normalized board or raise ValidationError.

    A board is a list of exactly ``size`` strings, each exactly ``size`` chars,
    using only symbols in SYMBOLS.
    """

    if not isinstance(board, list):
        raise ValidationError("board must be a list of strings")
    if len(board) != size:
        raise ValidationError(f"board must have exactly {size} rows")
    normalized: Board = []
    for row_index, row in enumerate(board):
        if not isinstance(row, str):
            raise ValidationError(f"row {row_index} must be a string")
        if len(row) != size:
            raise ValidationError(f"row {row_index} must have length {size}")
        invalid = set(row) - SYMBOLS
        if invalid:
            raise ValidationError(f"row {row_index} contains invalid symbols: {sorted(invalid)}")
        normalized.append(row)
    return normalized


def cells(size: int = BOARD_SIZE) -> Iterator[Coord]:
    for row in range(size):
        for col in range(size):
            yield row, col


def in_bounds(row: int, col: int, *, size: int = BOARD_SIZE) -> bool:
    return 0 <= row < size and 0 <= col < size


def relation_offsets(relation: str) -> tuple[Coord, ...]:
    if relation == "orthogonal":
        return ORTHOGONAL_OFFSETS
    if relation == "diagonal":
        return DIAGONAL_OFFSETS
    if relation == "king":
        return KING_OFFSETS
    raise ValidationError(f"unknown relation: {relation!r}")


def related_coords(row: int, col: int, relation: str, *, size: int = BOARD_SIZE) -> list[Coord]:
    coords: list[Coord] = []
    for dr, dc in relation_offsets(relation):
        nr, nc = row + dr, col + dc
        if in_bounds(nr, nc, size=size):
            coords.append((nr, nc))
    return coords


def count_relation(board: Sequence[str], row: int, col: int, relation: str) -> Counter[str]:
    board = validate_board(list(board))
    return Counter(board[r][c] for r, c in related_coords(row, col, relation, size=len(board)))


def local_stats(board: Sequence[str], row: int, col: int) -> LocalStats:
    board = validate_board(list(board))
    return LocalStats(
        target=board[row][col],
        orthogonal=count_relation(board, row, col, "orthogonal"),
        diagonal=count_relation(board, row, col, "diagonal"),
        king=count_relation(board, row, col, "king"),
    )


def evolve_cell(board: Sequence[str], row: int, col: int) -> str:
    """Deterministic public local evolution rule.

    Priority order matters and is part of the game:

    1. Empty cells become flowers when diagonal water and orthogonal flowers are
       present, unless any stone is in the king-neighborhood.
    2. Flowers with at least two neighboring stones wither into empty cells.
    3. Empty cells become water when exactly two orthogonal waters touch them
       and no diagonal stone touches them.
    4. Water trapped by having no orthogonal empty cells evaporates.
    5. Otherwise the cell stays unchanged.

    These public rules are intentionally small. The game is not to hide these
    rules; it is to state short, strong conjectures and to find sharp
    counterexamples.
    """

    board = validate_board(list(board))
    stats = local_stats(board, row, col)

    if (
        stats.target == "."
        and stats.diagonal["W"] >= 1
        and stats.orthogonal["F"] >= 1
        and stats.king["S"] == 0
    ):
        return "F"

    if stats.target == "F" and stats.king["S"] >= 2:
        return "."

    if stats.target == "." and stats.orthogonal["W"] == 2 and stats.diagonal["S"] == 0:
        return "W"

    if stats.target == "W" and stats.orthogonal["."] == 0:
        return "."

    return stats.target


def evolve(board: Sequence[str]) -> Board:
    """Return the next board under the public world rule."""

    board = validate_board(list(board))
    rows: list[str] = []
    for row in range(len(board)):
        chars = [evolve_cell(board, row, col) for col in range(len(board))]
        rows.append("".join(chars))
    return rows


def format_board(board: Sequence[str]) -> str:
    return "\n".join(validate_board(list(board)))


def tiny_local_boards(*, size: int = 3, symbols: Iterable[str] = SYMBOLS) -> Iterator[Board]:
    """Generate all boards of a tiny square size.

    This is used for exhaustive local checking. For the default 3x3 board and
    four symbols, this yields 4^9 = 262,144 boards, which is acceptable for
    occasional verification in this small game.
    """

    symbol_tuple = tuple(sorted(symbols))
    for chars in product(symbol_tuple, repeat=size * size):
        yield ["".join(chars[i * size : (i + 1) * size]) for i in range(size)]


def canonical_test_boards() -> list[Board]:
    """Small readable boards used by demo, tests, and scoring examples."""

    return [
        [".W...", ".....", "..F..", ".....", "....."],
        [".W...", ".....", ".SF..", ".....", "....."],
        ["WWWWW", "WFWFW", "WWWWW", "WSSSW", "WWWWW"],
        [".....", "..W..", ".W.W.", "..F..", "....."],
        ["SS...", ".F...", "..F..", "...W.", "....."],
    ]
