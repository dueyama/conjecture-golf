"""Canonical encodings for local Conjecture Golf patterns."""

from __future__ import annotations

from collections.abc import Sequence

from .world import ValidationError


def _validate_3x3(pattern: Sequence[str]) -> tuple[str, str, str]:
    if len(pattern) != 3 or any(not isinstance(row, str) or len(row) != 3 for row in pattern):
        raise ValidationError("pattern must be three strings of length 3")
    return tuple(pattern)  # type: ignore[return-value]


def _rotate_clockwise(pattern: tuple[str, str, str]) -> tuple[str, str, str]:
    return tuple("".join(pattern[2 - row][col] for row in range(3)) for col in range(3))  # type: ignore[return-value]


def _reflect_horizontal(pattern: tuple[str, str, str]) -> tuple[str, str, str]:
    return tuple(row[::-1] for row in pattern)  # type: ignore[return-value]


def d4_variants(pattern: Sequence[str]) -> tuple[tuple[str, str, str], ...]:
    base = _validate_3x3(pattern)
    variants: list[tuple[str, str, str]] = []
    current = base
    for _ in range(4):
        variants.append(current)
        variants.append(_reflect_horizontal(current))
        current = _rotate_clockwise(current)
    return tuple(variants)


def canonical_3x3(pattern: Sequence[str], *, use_d4: bool = True) -> str:
    base = _validate_3x3(pattern)
    variants = d4_variants(base) if use_d4 else (base,)
    return "/".join(min(variants))


def local_3x3_from_board(board: Sequence[str], row: int, col: int, *, pad: str = "#") -> tuple[str, str, str]:
    if len(pad) != 1:
        raise ValidationError("pad must be one character")
    rows: list[str] = []
    for rr in range(row - 1, row + 2):
        chars: list[str] = []
        for cc in range(col - 1, col + 2):
            if rr < 0 or cc < 0 or rr >= len(board) or cc >= len(board[rr]):
                chars.append(pad)
            else:
                chars.append(board[rr][cc])
        rows.append("".join(chars))
    return tuple(rows)  # type: ignore[return-value]


def witness_id(
    board: Sequence[str],
    cell: Sequence[int],
    *,
    expected: str,
    actual: str,
    use_d4: bool = True,
) -> str:
    if len(cell) != 2:
        raise ValidationError("cell must have row and col")
    row, col = int(cell[0]), int(cell[1])
    pattern = local_3x3_from_board(board, row, col)
    return f"expected={expected}:actual={actual}:pattern={canonical_3x3(pattern, use_d4=use_d4)}"
