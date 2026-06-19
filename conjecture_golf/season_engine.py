"""Compiled engine for data-only season specs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import cached_property
from itertools import product
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .season_spec import SeasonSpec, TransitionRule, load_season_spec
from .world import ValidationError, relation_offsets

Board = list[str]


@dataclass(frozen=True)
class LocalCenterContext:
    index: int
    local: tuple[str, ...]
    board: tuple[str, ...]
    center_before: str
    center_after: str


@dataclass(frozen=True)
class CompiledSeason:
    spec: SeasonSpec

    @property
    def symbol_set(self) -> set[str]:
        return self.spec.symbol_set

    @property
    def empty_symbol(self) -> str:
        return "."

    def validate_board(self, board: Sequence[str]) -> Board:
        if not isinstance(board, list):
            raise ValidationError("board must be a list of strings")
        if len(board) != self.spec.height:
            raise ValidationError(f"board must have exactly {self.spec.height} rows")
        normalized: Board = []
        for row_index, row in enumerate(board):
            if not isinstance(row, str):
                raise ValidationError(f"row {row_index} must be a string")
            if len(row) != self.spec.width:
                raise ValidationError(f"row {row_index} must have length {self.spec.width}")
            invalid = set(row) - self.symbol_set
            if invalid:
                raise ValidationError(f"row {row_index} contains invalid symbols: {sorted(invalid)}")
            normalized.append(row)
        return normalized

    def related_coords(self, row: int, col: int, relation: str) -> list[tuple[int, int]]:
        if relation not in self.spec.relations:
            raise ValidationError(f"unknown relation: {relation!r}")
        coords: list[tuple[int, int]] = []
        for dr, dc in relation_offsets(relation):
            nr, nc = row + dr, col + dc
            if 0 <= nr < self.spec.height and 0 <= nc < self.spec.width:
                coords.append((nr, nc))
        return coords

    def relation_counts(self, board: Sequence[str], row: int, col: int, relation: str) -> Counter[str]:
        return Counter(board[r][c] for r, c in self.related_coords(row, col, relation))

    def evaluate_condition(self, board: Sequence[str], row: int, col: int, condition: Mapping[str, Any]) -> bool:
        key = next(iter(condition))
        value = condition[key]
        if key == "target_is":
            return board[row][col] == value

        counts = self.relation_counts(board, row, col, value["relation"])
        symbol = value["symbol"]
        if key == "exists":
            return counts[symbol] >= 1
        if key == "not_exists":
            return counts[symbol] == 0
        if key == "count_at_least":
            return counts[symbol] >= int(value["n"])
        if key == "count_exactly":
            return counts[symbol] == int(value["n"])
        raise ValidationError(f"unknown condition kind: {key}")

    def evaluate_conditions(self, board: Sequence[str], row: int, col: int, conditions: Sequence[Mapping[str, Any]]) -> bool:
        return all(self.evaluate_condition(board, row, col, condition) for condition in conditions)

    def first_matching_rule(self, board: Sequence[str], row: int, col: int) -> TransitionRule | None:
        for rule in self.spec.rules:
            if self.evaluate_conditions(board, row, col, rule.when):
                return rule
        return None

    def _next_symbol_for_cell_unchecked(self, board: Sequence[str], row: int, col: int) -> str:
        rule = self.first_matching_rule(board, row, col)
        if rule is not None:
            return rule.becomes
        return board[row][col]

    def next_symbol_for_cell(self, board: Sequence[str], row: int, col: int) -> str:
        board = self.validate_board(list(board))
        return self._next_symbol_for_cell_unchecked(board, row, col)

    def step_board(self, board: Sequence[str]) -> Board:
        board = self.validate_board(list(board))
        rows: list[str] = []
        for row in range(self.spec.height):
            chars = [self._next_symbol_for_cell_unchecked(board, row, col) for col in range(self.spec.width)]
            rows.append("".join(chars))
        return rows

    def center_embed_3x3(self, local: Sequence[str]) -> Board:
        if len(local) != 3 or any(len(row) != 3 for row in local):
            raise ValidationError("local board must be 3x3")
        board = [list(self.empty_symbol * self.spec.width) for _ in range(self.spec.height)]
        for row in range(3):
            for col in range(3):
                ch = local[row][col]
                if ch not in self.symbol_set:
                    raise ValidationError("local board contains invalid symbols")
                board[row + 1][col + 1] = ch
        return ["".join(row) for row in board]

    def tiny_local_boards(self, *, size: int = 3) -> Iterable[Board]:
        symbol_tuple = tuple(sorted(self.symbol_set))
        for chars in product(symbol_tuple, repeat=size * size):
            yield ["".join(chars[i * size : (i + 1) * size]) for i in range(size)]

    @cached_property
    def local_center_contexts(self) -> tuple[LocalCenterContext, ...]:
        contexts: list[LocalCenterContext] = []
        for index, local in enumerate(self.tiny_local_boards(size=3)):
            board = tuple(local)
            contexts.append(
                LocalCenterContext(
                    index=index,
                    local=board,
                    board=board,
                    center_before=board[1][1],
                    center_after=self._next_symbol_for_cell_unchecked(board, 1, 1),
                )
            )
        return tuple(contexts)

    def validate_conjecture(self, conjecture: Any) -> dict[str, Any]:
        if not isinstance(conjecture, Mapping):
            raise ValidationError("conjecture must be an object")
        raw = dict(conjecture)
        allowed = {"name", "if", "then", "player", "description", "tags", "claim_kind"}
        unknown = set(raw) - allowed
        if unknown:
            raise ValidationError(f"unknown conjecture fields: {sorted(unknown)}")
        missing = {"name", "if", "then"} - set(raw)
        if missing:
            raise ValidationError(f"missing conjecture fields: {sorted(missing)}")
        name = self._validate_name(raw["name"])
        claim_kind = raw.get("claim_kind", "sufficient")
        if claim_kind not in self.spec.conjecture_dsl.claim_kinds:
            raise ValidationError(f"claim_kind must be one of {sorted(self.spec.conjecture_dsl.claim_kinds)}")
        conditions_raw = raw["if"]
        if not isinstance(conditions_raw, list) or not conditions_raw:
            raise ValidationError("conjecture 'if' must be a non-empty list")
        if len(conditions_raw) > self.spec.conjecture_dsl.max_conditions:
            raise ValidationError("conjecture has too many conditions")
        conditions = [self._validate_condition(condition) for condition in conditions_raw]
        then = raw["then"]
        if not isinstance(then, Mapping) or set(then) != {"target_becomes"}:
            raise ValidationError("then must contain exactly target_becomes")
        target_becomes = then["target_becomes"]
        if target_becomes not in self.symbol_set:
            raise ValidationError(f"target_becomes must be one of {sorted(self.symbol_set)}")
        normalized: dict[str, Any] = {
            "name": name,
            "claim_kind": claim_kind,
            "if": conditions,
            "then": {"target_becomes": target_becomes},
        }
        if "player" in raw:
            if not isinstance(raw["player"], str) or len(raw["player"].strip()) > 80:
                raise ValidationError("player must be a short string")
            normalized["player"] = raw["player"].strip()
        if "description" in raw:
            if not isinstance(raw["description"], str) or len(raw["description"]) > 500:
                raise ValidationError("description must be a string no longer than 500 chars")
            normalized["description"] = raw["description"]
        if "tags" in raw:
            tags = raw["tags"]
            if not isinstance(tags, list) or len(tags) > 10 or not all(isinstance(t, str) and len(t) <= 40 for t in tags):
                raise ValidationError("tags must be a list of up to ten short strings")
            normalized["tags"] = list(tags)
        return normalized

    def conjecture_complexity(self, conjecture: Mapping[str, Any]) -> int:
        normalized = self.validate_conjecture(conjecture)
        cost = 0
        for condition in normalized["if"]:
            kind = next(iter(condition))
            cost += 1
            if kind in {"exists", "not_exists", "count_at_least", "count_exactly"}:
                cost += 1
            if kind in {"count_at_least", "count_exactly"}:
                cost += 1
        claim_kind = normalized.get("claim_kind", "sufficient")
        if claim_kind == "necessary":
            cost += 1
        elif claim_kind == "equivalence":
            cost += 2
        return cost + 1

    def conjecture_antecedent_matches(self, conjecture: Mapping[str, Any], board: Sequence[str], row: int, col: int) -> bool:
        normalized = self.validate_conjecture(conjecture)
        board = self.validate_board(list(board))
        return self.evaluate_conditions(board, row, col, normalized["if"])

    def _validate_condition(self, condition: Any) -> dict[str, Any]:
        if not isinstance(condition, Mapping):
            raise ValidationError("condition must be an object")
        raw = dict(condition)
        if len(raw) != 1:
            raise ValidationError("each condition must contain exactly one condition kind")
        key = next(iter(raw))
        if key not in self.spec.conjecture_dsl.condition_kinds:
            raise ValidationError(f"unknown condition kind: {key}")
        if key == "target_is":
            symbol = raw[key]
            if symbol not in self.symbol_set:
                raise ValidationError(f"target_is must be one of {sorted(self.symbol_set)}")
            return {"target_is": symbol}
        value = raw[key]
        if not isinstance(value, Mapping):
            raise ValidationError(f"{key} condition must be an object")
        required = {"symbol", "relation"} if key in {"exists", "not_exists"} else {"symbol", "relation", "n"}
        if set(value) != required:
            raise ValidationError(f"{key} condition must have {sorted(required)}")
        symbol = value["symbol"]
        relation = value["relation"]
        if symbol not in self.symbol_set:
            raise ValidationError(f"condition symbol must be one of {sorted(self.symbol_set)}")
        if relation not in self.spec.relations:
            raise ValidationError(f"relation must be one of {sorted(self.spec.relations)}")
        normalized: dict[str, Any] = {key: {"symbol": symbol, "relation": relation}}
        if key in {"count_at_least", "count_exactly"}:
            n = value["n"]
            if not isinstance(n, int) or n < 0 or n > 8:
                raise ValidationError("n must be an integer from 0 to 8")
            if (
                key == "count_at_least"
                and n == 0
                and self.spec.conjecture_dsl.trivial_count_policy == "reject_count_at_least_zero"
            ):
                raise ValidationError("count_at_least with n=0 is not allowed in this season")
            normalized[key]["n"] = n
        return normalized

    @staticmethod
    def _validate_name(name: Any) -> str:
        if not isinstance(name, str):
            raise ValidationError("conjecture name must be a string")
        cleaned = name.strip()
        if not cleaned:
            raise ValidationError("conjecture name must not be empty")
        if len(cleaned) > 80:
            raise ValidationError("conjecture name is too long")
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")
        if any(ch not in allowed for ch in cleaned):
            raise ValidationError("conjecture name may contain only letters, digits, '_', '-', and '.'")
        return cleaned


def compile_season(spec: SeasonSpec) -> CompiledSeason:
    return CompiledSeason(spec=spec)


def load_compiled_season(path: str | Path) -> CompiledSeason:
    return compile_season(load_season_spec(path))
