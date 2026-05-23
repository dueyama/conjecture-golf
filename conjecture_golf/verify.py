"""Verification CLI and library for Conjecture Golf."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .dsl import antecedent_matches, complexity, player_name_from_submission, validate_conjecture
from .season_catalog import load_optional_compiled_season
from .season_engine import CompiledSeason
from .world import BOARD_SIZE, Board, ValidationError, canonical_test_boards, evolve, format_board, related_coords, tiny_local_boards, validate_board

_DEFAULT_CONJECTURE_VERDICT_CACHE: dict[tuple[str, bool], Verdict] = {}
_SEASON_CONJECTURE_VERDICT_CACHE: dict[tuple[str, str, bool], Verdict] = {}
_MAX_VERDICT_CACHE_SIZE = 512


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


def _digest_payload(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _season_cache_key(season: CompiledSeason) -> str:
    return _canonical_json(season.spec.raw)


def _clone_verdict(verdict: Verdict) -> Verdict:
    return replace(verdict, details=copy.deepcopy(verdict.details))


def _remember_verdict(cache: dict[Any, Verdict], key: Any, verdict: Verdict) -> None:
    if len(cache) >= _MAX_VERDICT_CACHE_SIZE:
        cache.clear()
    cache[key] = _clone_verdict(verdict)


def redact_verdict(verdict: Verdict, *, reveal_policy: str = "full") -> Verdict:
    if reveal_policy == "full":
        return verdict
    if reveal_policy != "redacted":
        raise ValidationError("reveal_policy must be full or redacted")

    details = verdict.details
    if verdict.kind != "conjecture" or verdict.ok or not isinstance(details, dict):
        return verdict
    counterexample = details.get("counterexample")
    if not isinstance(counterexample, dict):
        return verdict

    redacted = dict(details)
    redacted["counterexample_redacted"] = True
    redacted["counterexample_digest"] = _digest_payload(counterexample)
    redacted["counterexample_summary"] = {
        "expected": counterexample.get("expected"),
        "actual": counterexample.get("actual"),
    }
    redacted.pop("counterexample", None)
    return replace(
        verdict,
        message=f"{verdict.message} Counterexample witness redacted by reveal policy.",
        details=redacted,
    )


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


def _verify_conjecture_with_season(
    conjecture: Mapping[str, Any],
    *,
    season: CompiledSeason,
    exhaustive_local: bool,
) -> Verdict:
    try:
        normalized = season.validate_conjecture(conjecture)
        player = player_name_from_submission(normalized)
        obligations_checked = 0
        counterexamples: list[dict[str, Any]] = []
        expected = normalized["then"]["target_becomes"]
        claim_kind = normalized.get("claim_kind", "sufficient")

        if exhaustive_local:
            contexts = season.local_center_contexts
        else:
            boards = [board for board in canonical_test_boards() if set("".join(board)) <= season.symbol_set]

        if exhaustive_local:
            for context in contexts:
                board = context.board
                row, col = 1, 1
                antecedent = season.evaluate_conditions(board, row, col, normalized["if"])
                actual = context.center_after
                target_produced = actual == expected
                if claim_kind in {"sufficient", "equivalence"} and antecedent:
                    obligations_checked += 1
                if claim_kind == "necessary" and target_produced:
                    obligations_checked += 1
                if (
                    (claim_kind in {"sufficient", "equivalence"} and antecedent and not target_produced)
                    or (claim_kind in {"necessary", "equivalence"} and target_produced and not antecedent)
                ):
                    witness_board = season.center_embed_3x3(context.local)
                    counterexamples.append(
                        {
                            "board": witness_board,
                            "after": season.step_board(witness_board),
                            "cell": [2, 2],
                            "expected": expected,
                            "actual": actual,
                            "claim_kind": claim_kind,
                            "antecedent": antecedent,
                        }
                    )
                    break
        else:
            for board in boards:
                for row in range(len(board)):
                    for col in range(len(board[row])):
                        antecedent = season.evaluate_conditions(board, row, col, normalized["if"])
                        actual = season.next_symbol_for_cell(board, row, col)
                        target_produced = actual == expected
                        if claim_kind in {"sufficient", "equivalence"} and antecedent:
                            obligations_checked += 1
                        if claim_kind == "necessary" and target_produced:
                            obligations_checked += 1
                        if (
                            (claim_kind in {"sufficient", "equivalence"} and antecedent and not target_produced)
                            or (claim_kind in {"necessary", "equivalence"} and target_produced and not antecedent)
                        ):
                            counterexamples.append(
                                {
                                    "board": board,
                                    "after": season.step_board(board),
                                    "cell": [row, col],
                                    "expected": expected,
                                    "actual": actual,
                                    "claim_kind": claim_kind,
                                    "antecedent": antecedent,
                                }
                            )
                            break
                    if counterexamples:
                        break
                if counterexamples:
                    break

        comp = season.conjecture_complexity(normalized)
        if counterexamples:
            return Verdict(
                ok=False,
                kind="conjecture",
                player=player,
                message=f"Conjecture {normalized['name']!r} is false; a counterexample was found.",
                score_delta=-5,
                details={
                    "name": normalized["name"],
                    "claim_kind": claim_kind,
                    "complexity": comp,
                    "obligations_checked_before_failure": obligations_checked,
                    "counterexample": counterexamples[0],
                    "season_id": season.spec.season_id,
                },
            )

        if obligations_checked == 0:
            return Verdict(
                ok=False,
                kind="conjecture",
                player=player,
                message=f"Conjecture {normalized['name']!r} is vacuous on the exhaustive local check.",
                score_delta=-5,
                details={"name": normalized["name"], "claim_kind": claim_kind, "complexity": comp, "coverage": 0, "season_id": season.spec.season_id},
            )

        coverage_bonus = min(40, obligations_checked // 512)
        if claim_kind == "necessary":
            coverage_bonus = min(40, obligations_checked // 1024)
        elif claim_kind == "equivalence":
            coverage_bonus = min(60, obligations_checked // 512)
        score_delta = max(1, 10 + coverage_bonus - comp)
        return Verdict(
            ok=True,
            kind="conjecture",
            player=player,
            message=f"Conjecture {normalized['name']!r} holds on the exhaustive local check.",
            score_delta=score_delta,
            details={
                "name": normalized["name"],
                "claim_kind": claim_kind,
                "complexity": comp,
                "coverage": obligations_checked,
                "coverage_bonus": coverage_bonus,
                "season_id": season.spec.season_id,
            },
        )
    except ValidationError as exc:
        return Verdict(ok=False, kind="conjecture", message=str(exc), score_delta=-5)


def verify_conjecture(
    conjecture: Mapping[str, Any],
    *,
    exhaustive_local: bool = True,
    season: CompiledSeason | None = None,
) -> Verdict:
    try:
        if season is not None:
            normalized = season.validate_conjecture(conjecture)
            cache_key = (_season_cache_key(season), _canonical_json(normalized), exhaustive_local)
            cached = _SEASON_CONJECTURE_VERDICT_CACHE.get(cache_key)
            if cached is not None:
                return _clone_verdict(cached)
            verdict = _verify_conjecture_uncached(
                normalized,
                exhaustive_local=exhaustive_local,
                season=season,
            )
            _remember_verdict(_SEASON_CONJECTURE_VERDICT_CACHE, cache_key, verdict)
            return _clone_verdict(verdict)

        normalized = validate_conjecture(conjecture)
        cache_key = (_canonical_json(normalized), exhaustive_local)
        cached = _DEFAULT_CONJECTURE_VERDICT_CACHE.get(cache_key)
        if cached is not None:
            return _clone_verdict(cached)
        verdict = _verify_conjecture_uncached(normalized, exhaustive_local=exhaustive_local)
        _remember_verdict(_DEFAULT_CONJECTURE_VERDICT_CACHE, cache_key, verdict)
        return _clone_verdict(verdict)
    except ValidationError as exc:
        return Verdict(ok=False, kind="conjecture", message=str(exc), score_delta=-5)


def _verify_conjecture_uncached(
    conjecture: Mapping[str, Any],
    *,
    exhaustive_local: bool = True,
    season: CompiledSeason | None = None,
) -> Verdict:
    """Verify whether a conjecture is true for the public world rule.

    The MVP checks all possible 3x3 neighborhoods around the center cell by
    embedding them into a 5x5 board. Because the public evolution rule is local,
    this is a meaningful and deterministic check for the center cell.
    """

    if season is not None:
        return _verify_conjecture_with_season(conjecture, season=season, exhaustive_local=exhaustive_local)

    try:
        normalized = validate_conjecture(conjecture)
        player = player_name_from_submission(normalized)
        obligations_checked = 0
        counterexamples: list[dict[str, Any]] = []

        expected = normalized["then"]["target_becomes"]
        claim_kind = normalized.get("claim_kind", "sufficient")
        if exhaustive_local:
            # Check the center cell for every possible 3x3 local neighborhood.
            # This is fast enough and avoids full-board repeated validation.
            for local in tiny_local_boards(size=3):
                board = _center_embed_3x3(local)
                row, col = 2, 2
                antecedent = _antecedent_matches_fast(normalized, board, row, col)
                actual = _evolve_cell_fast(board, row, col)
                target_produced = actual == expected
                if claim_kind in {"sufficient", "equivalence"} and antecedent:
                    obligations_checked += 1
                if claim_kind == "necessary" and target_produced:
                    obligations_checked += 1
                if (
                    (claim_kind in {"sufficient", "equivalence"} and antecedent and not target_produced)
                    or (claim_kind in {"necessary", "equivalence"} and target_produced and not antecedent)
                ):
                    counterexamples.append(
                        {
                            "board": board,
                            "after": evolve(board),
                            "cell": [row, col],
                            "expected": expected,
                            "actual": actual,
                            "claim_kind": claim_kind,
                            "antecedent": antecedent,
                        }
                    )
                    break
        else:
            for board in canonical_test_boards():
                for row in range(BOARD_SIZE):
                    for col in range(BOARD_SIZE):
                        antecedent = _antecedent_matches_fast(normalized, board, row, col)
                        actual = _evolve_cell_fast(board, row, col)
                        target_produced = actual == expected
                        if claim_kind in {"sufficient", "equivalence"} and antecedent:
                            obligations_checked += 1
                        if claim_kind == "necessary" and target_produced:
                            obligations_checked += 1
                        if (
                            (claim_kind in {"sufficient", "equivalence"} and antecedent and not target_produced)
                            or (claim_kind in {"necessary", "equivalence"} and target_produced and not antecedent)
                        ):
                            counterexamples.append(
                                {
                                    "board": board,
                                    "after": evolve(board),
                                    "cell": [row, col],
                                    "expected": expected,
                                    "actual": actual,
                                    "claim_kind": claim_kind,
                                    "antecedent": antecedent,
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
                    "claim_kind": claim_kind,
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
                details={"name": normalized["name"], "claim_kind": claim_kind, "complexity": comp, "coverage": 0},
            )

        coverage_bonus = min(40, obligations_checked // 512)
        if claim_kind == "necessary":
            coverage_bonus = min(40, obligations_checked // 1024)
        elif claim_kind == "equivalence":
            coverage_bonus = min(60, obligations_checked // 512)
        score_delta = max(1, 10 + coverage_bonus - comp)
        return Verdict(
            ok=True,
            kind="conjecture",
            player=player,
            message=f"Conjecture {normalized['name']!r} holds on the exhaustive local check.",
            score_delta=score_delta,
            details={
                "name": normalized["name"],
                "claim_kind": claim_kind,
                "complexity": comp,
                "coverage": obligations_checked,
                "coverage_bonus": coverage_bonus,
            },
        )
    except ValidationError as exc:
        return Verdict(ok=False, kind="conjecture", message=str(exc), score_delta=-5)


def local_obligation_keys(conjecture: Mapping[str, Any]) -> set[str]:
    """Return deterministic local obligations covered by a normalized conjecture.

    This legacy wrapper returns stable obligation IDs from
    ``conjecture_golf.obligations``.
    """

    from .obligations import obligation_ids_for_conjecture

    return set(obligation_ids_for_conjecture(conjecture))


def _check_counterexample_with_season(conjecture: Mapping[str, Any], before: Sequence[str], *, season: CompiledSeason) -> Verdict:
    try:
        normalized = season.validate_conjecture(conjecture)
        board = season.validate_board(list(before))
        expected = normalized["then"]["target_becomes"]
        claim_kind = normalized.get("claim_kind", "sufficient")
        obligations: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for row in range(season.spec.height):
            for col in range(season.spec.width):
                antecedent = season.evaluate_conditions(board, row, col, normalized["if"])
                actual = season.next_symbol_for_cell(board, row, col)
                target_produced = actual == expected
                if claim_kind in {"sufficient", "equivalence"} and antecedent:
                    item = {
                        "row": row,
                        "col": col,
                        "expected": expected,
                        "actual": actual,
                        "holds": target_produced,
                        "claim_kind": claim_kind,
                        "antecedent": antecedent,
                    }
                    obligations.append(item)
                    if not item["holds"]:
                        failures.append(item)
                if claim_kind in {"necessary", "equivalence"} and target_produced:
                    item = {
                        "row": row,
                        "col": col,
                        "expected": expected,
                        "actual": actual,
                        "holds": antecedent,
                        "claim_kind": claim_kind,
                        "antecedent": antecedent,
                    }
                    obligations.append(item)
                    if not item["holds"]:
                        failures.append(item)
        player = player_name_from_submission(normalized)
        if not failures:
            return Verdict(
                ok=False,
                kind="counterexample",
                player=player,
                message="The board is not a counterexample; every triggered obligation holds.",
                score_delta=-5,
                details={"obligations": len(obligations), "before": board, "after": season.step_board(board), "season_id": season.spec.season_id},
            )
        first = failures[0]
        occupied = sum(ch != "." for row in board for ch in row)
        minimality_bonus = max(0, 15 - occupied)
        return Verdict(
            ok=True,
            kind="counterexample",
            player=player,
            message=f"Valid counterexample against {normalized['name']!r} at cell ({first['row']}, {first['col']}).",
            score_delta=20 + minimality_bonus,
            details={
                "name": normalized["name"],
                "before": board,
                "after": season.step_board(board),
                "cell": [first["row"], first["col"]],
                "expected": first["expected"],
                "actual": first["actual"],
                "minimality_bonus": minimality_bonus,
                "season_id": season.spec.season_id,
            },
        )
    except ValidationError as exc:
        return Verdict(ok=False, kind="counterexample", message=str(exc), score_delta=-5)


def check_counterexample(
    conjecture: Mapping[str, Any],
    before: Sequence[str],
    *,
    season: CompiledSeason | None = None,
) -> Verdict:
    """Check whether a board is a valid counterexample to a conjecture.

    The supplied board is the before-state. The verifier computes the after-state
    using the public world rule. A counterexample is valid when some target cell
    satisfies the conjecture's antecedent but evolves to a symbol different from
    the conjecture's consequent.
    """

    if season is not None:
        return _check_counterexample_with_season(conjecture, before, season=season)

    try:
        normalized = validate_conjecture(conjecture)
        board = validate_board(list(before))
        expected = normalized["then"]["target_becomes"]
        claim_kind = normalized.get("claim_kind", "sufficient")
        obligations: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                antecedent = antecedent_matches(normalized, board, row, col)
                actual = _evolve_cell_fast(board, row, col)
                target_produced = actual == expected
                if claim_kind in {"sufficient", "equivalence"} and antecedent:
                    item = {
                        "row": row,
                        "col": col,
                        "expected": expected,
                        "actual": actual,
                        "holds": target_produced,
                        "claim_kind": claim_kind,
                        "antecedent": antecedent,
                    }
                    obligations.append(item)
                    if not item["holds"]:
                        failures.append(item)
                if claim_kind in {"necessary", "equivalence"} and target_produced:
                    item = {
                        "row": row,
                        "col": col,
                        "expected": expected,
                        "actual": actual,
                        "holds": antecedent,
                        "claim_kind": claim_kind,
                        "antecedent": antecedent,
                    }
                    obligations.append(item)
                    if not item["holds"]:
                        failures.append(item)
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


def verify_file(path: str | Path, *, season: CompiledSeason | None = None) -> Verdict:
    payload = load_json(path)
    if not isinstance(payload, dict):
        return Verdict(ok=False, kind="file", message="top-level JSON must be an object", score_delta=-5)
    if payload.get("type") == "counterexample":
        conjecture = payload.get("conjecture")
        before = payload.get("before") or payload.get("board")
        if conjecture is None or before is None:
            return Verdict(ok=False, kind="counterexample", message="counterexample file needs conjecture and before/board", score_delta=-5)
        return check_counterexample(conjecture, before, season=season)
    if payload.get("type") == "conjecture":
        payload = {k: v for k, v in payload.items() if k != "type"}
    return verify_conjecture(payload, season=season)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a Conjecture Golf JSON file.")
    parser.add_argument("path", help="Path to a conjecture or counterexample JSON file")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON verdict")
    parser.add_argument("--reveal-policy", choices=["full", "redacted"], default="full")
    parser.add_argument("--season", help="Optional data-only season spec path")
    args = parser.parse_args(argv)
    season = load_optional_compiled_season(args.season)
    verdict = verify_file(args.path, season=season)
    verdict = redact_verdict(verdict, reveal_policy=args.reveal_policy)
    indent = 2 if args.pretty else None
    print(json.dumps(verdict.to_dict(), ensure_ascii=False, indent=indent))
    return 0 if verdict.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
