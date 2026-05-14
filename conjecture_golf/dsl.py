"""JSON-compatible conjecture DSL for Conjecture Golf."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .world import RELATIONS, SYMBOLS, Board, ValidationError, count_relation, evolve_cell, validate_board

ALLOWED_CONDITION_KEYS = {"target_is", "exists", "not_exists", "count_at_least", "count_exactly"}
ALLOWED_THEN_KEYS = {"target_becomes"}
REQUIRED_CONJECTURE_KEYS = {"name", "if", "then"}
CLAIM_KINDS = {"sufficient", "necessary", "equivalence"}
ALLOWED_CONJECTURE_KEYS = REQUIRED_CONJECTURE_KEYS | {"player", "description", "tags", "claim_kind"}


Conjecture = dict[str, Any]
Condition = dict[str, Any]


def _require_mapping(obj: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(obj, Mapping):
        raise ValidationError(f"{label} must be an object")
    return obj


def _validate_symbol(symbol: Any, label: str = "symbol") -> str:
    if not isinstance(symbol, str) or symbol not in SYMBOLS:
        raise ValidationError(f"{label} must be one of {sorted(SYMBOLS)}")
    return symbol


def _validate_relation(relation: Any) -> str:
    if not isinstance(relation, str) or relation not in RELATIONS:
        raise ValidationError(f"relation must be one of {sorted(RELATIONS)}")
    return relation


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


def _validate_claim_kind(claim_kind: Any) -> str:
    if claim_kind is None:
        return "sufficient"
    if not isinstance(claim_kind, str) or claim_kind not in CLAIM_KINDS:
        raise ValidationError(f"claim_kind must be one of {sorted(CLAIM_KINDS)}")
    return claim_kind


def validate_condition(condition: Any) -> Condition:
    condition = dict(_require_mapping(condition, "condition"))
    keys = set(condition)
    if len(keys) != 1:
        raise ValidationError("each condition must contain exactly one condition kind")
    key = next(iter(keys))
    if key not in ALLOWED_CONDITION_KEYS:
        raise ValidationError(f"unknown condition kind: {key}")

    if key == "target_is":
        return {"target_is": _validate_symbol(condition[key], "target_is")}

    body = _require_mapping(condition[key], key)
    body_keys = set(body)

    if key in {"exists", "not_exists"}:
        if body_keys != {"symbol", "relation"}:
            raise ValidationError(f"{key} condition must have symbol and relation")
        return {
            key: {
                "symbol": _validate_symbol(body["symbol"]),
                "relation": _validate_relation(body["relation"]),
            }
        }

    if key in {"count_at_least", "count_exactly"}:
        if body_keys != {"symbol", "relation", "n"}:
            raise ValidationError(f"{key} condition must have symbol, relation, and n")
        n = body["n"]
        if not isinstance(n, int) or n < 0 or n > 8:
            raise ValidationError("n must be an integer from 0 to 8")
        return {
            key: {
                "symbol": _validate_symbol(body["symbol"]),
                "relation": _validate_relation(body["relation"]),
                "n": n,
            }
        }

    raise AssertionError("unreachable")


def validate_conjecture(conjecture: Any) -> Conjecture:
    conjecture = dict(_require_mapping(conjecture, "conjecture"))
    unknown = set(conjecture) - ALLOWED_CONJECTURE_KEYS
    if unknown:
        raise ValidationError(f"unknown conjecture fields: {sorted(unknown)}")
    missing = REQUIRED_CONJECTURE_KEYS - set(conjecture)
    if missing:
        raise ValidationError(f"missing conjecture fields: {sorted(missing)}")

    name = _validate_name(conjecture["name"])
    if_conditions = conjecture["if"]
    if not isinstance(if_conditions, list) or not if_conditions:
        raise ValidationError("conjecture 'if' must be a non-empty list")
    if len(if_conditions) > 8:
        raise ValidationError("conjecture has too many conditions; maximum is 8")
    conditions = [validate_condition(item) for item in if_conditions]

    then = dict(_require_mapping(conjecture["then"], "then"))
    if set(then) != ALLOWED_THEN_KEYS:
        raise ValidationError("then must contain exactly target_becomes")
    then = {"target_becomes": _validate_symbol(then["target_becomes"], "target_becomes")}

    normalized: Conjecture = {
        "name": name,
        "claim_kind": _validate_claim_kind(conjecture.get("claim_kind")),
        "if": conditions,
        "then": then,
    }
    if "player" in conjecture:
        if not isinstance(conjecture["player"], str) or len(conjecture["player"].strip()) > 80:
            raise ValidationError("player must be a short string")
        normalized["player"] = conjecture["player"].strip()
    if "description" in conjecture:
        if not isinstance(conjecture["description"], str) or len(conjecture["description"]) > 500:
            raise ValidationError("description must be a string no longer than 500 chars")
        normalized["description"] = conjecture["description"]
    if "tags" in conjecture:
        tags = conjecture["tags"]
        if not isinstance(tags, list) or len(tags) > 10 or not all(isinstance(t, str) and len(t) <= 40 for t in tags):
            raise ValidationError("tags must be a list of up to ten short strings")
        normalized["tags"] = list(tags)
    return normalized


def condition_matches(condition: Condition, board: Sequence[str], row: int, col: int) -> bool:
    board = validate_board(list(board))
    key = next(iter(condition))
    value = condition[key]

    if key == "target_is":
        return board[row][col] == value

    if key == "exists":
        counts = count_relation(board, row, col, value["relation"])
        return counts[value["symbol"]] >= 1

    if key == "not_exists":
        counts = count_relation(board, row, col, value["relation"])
        return counts[value["symbol"]] == 0

    if key == "count_at_least":
        counts = count_relation(board, row, col, value["relation"])
        return counts[value["symbol"]] >= value["n"]

    if key == "count_exactly":
        counts = count_relation(board, row, col, value["relation"])
        return counts[value["symbol"]] == value["n"]

    raise ValidationError(f"unknown condition kind: {key}")


def antecedent_matches(conjecture: Mapping[str, Any], board: Sequence[str], row: int, col: int) -> bool:
    conjecture = validate_conjecture(conjecture)
    return all(condition_matches(condition, board, row, col) for condition in conjecture["if"])


def predicted_symbol(conjecture: Mapping[str, Any]) -> str:
    conjecture = validate_conjecture(conjecture)
    return conjecture["then"]["target_becomes"]


def evaluate_on_board(conjecture: Mapping[str, Any], board: Sequence[str]) -> list[dict[str, Any]]:
    """Return per-cell obligations implied by a conjecture on a board."""

    board = validate_board(list(board))
    conjecture = validate_conjecture(conjecture)
    obligations: list[dict[str, Any]] = []
    expected = predicted_symbol(conjecture)
    claim_kind = conjecture.get("claim_kind", "sufficient")
    for row in range(len(board)):
        for col in range(len(board)):
            antecedent = antecedent_matches(conjecture, board, row, col)
            actual = evolve_cell(board, row, col)
            target_produced = actual == expected
            if claim_kind in {"sufficient", "equivalence"} and antecedent:
                obligations.append(
                    {
                        "row": row,
                        "col": col,
                        "expected": expected,
                        "actual": actual,
                        "holds": target_produced,
                        "claim_kind": claim_kind,
                        "antecedent": antecedent,
                    }
                )
            if claim_kind in {"necessary", "equivalence"} and target_produced:
                obligations.append(
                    {
                        "row": row,
                        "col": col,
                        "expected": expected,
                        "actual": actual,
                        "holds": antecedent,
                        "claim_kind": claim_kind,
                        "antecedent": antecedent,
                    }
                )
    return obligations


def complexity(conjecture: Mapping[str, Any]) -> int:
    """A simple deterministic complexity measure for scoring."""

    conjecture = validate_conjecture(conjecture)
    cost = 0
    for condition in conjecture["if"]:
        kind = next(iter(condition))
        cost += 1
        if kind in {"exists", "not_exists", "count_at_least", "count_exactly"}:
            cost += 1
        if kind in {"count_at_least", "count_exactly"}:
            cost += 1
    claim_kind = conjecture.get("claim_kind", "sufficient")
    if claim_kind == "necessary":
        cost += 1
    elif claim_kind == "equivalence":
        cost += 2
    return cost + 1  # then-clause cost


def player_name_from_submission(submission: Mapping[str, Any], *, fallback: str = "anonymous") -> str:
    player = submission.get("player", fallback)
    if not isinstance(player, str):
        return fallback
    player = player.strip()
    if not player or len(player) > 80:
        return fallback
    return player
