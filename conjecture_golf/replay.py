"""Replay transcripts for Conjecture Golf.

A transcript is a JSONL file. Each line is one public command. Replaying the
same transcript must always produce the same final score.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .agent_profile import validate_hello_command
from .dsl import player_name_from_submission, validate_conjecture
from .canonical import witness_id
from .obligations import ObligationLedger, obligation_ids_for_conjecture, summarize_obligation_ids
from .score import PlayerScore, apply_verdict, leaderboard_rows, render_markdown
from .season_catalog import load_optional_compiled_season
from .season_engine import CompiledSeason
from .verify import Verdict, check_counterexample, verify_conjecture
from .world import ValidationError


@dataclass
class ReplayState:
    conjectures: dict[str, dict[str, Any]] = field(default_factory=dict)
    scores: dict[str, PlayerScore] = field(default_factory=dict)
    verdicts: list[Verdict] = field(default_factory=list)
    agent_profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_command_at_by_player: dict[str, datetime] = field(default_factory=dict)
    obligation_ledger: ObligationLedger = field(default_factory=ObligationLedger)
    conjecture_signatures: set[str] = field(default_factory=set)
    auto_counterexamples: dict[str, tuple[str, ...]] = field(default_factory=dict)
    auto_counterexample_witness_ids: dict[str, str] = field(default_factory=dict)
    known_witness_ids: set[str] = field(default_factory=set)
    countered_conjectures: set[str] = field(default_factory=set)
    conjecture_target_values: dict[str, int] = field(default_factory=dict)

    def apply(self, verdict: Verdict) -> None:
        self.verdicts.append(verdict)
        apply_verdict(self.scores, verdict)


def normalize_command(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ValidationError("transcript record must be an object")
    command_type = record.get("type")
    if command_type not in {"hello", "conjecture", "counterexample", "score", "invalid"}:
        raise ValidationError("record type must be hello, conjecture, counterexample, score, or invalid")
    return dict(record)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _conjecture_signature(conjecture: Mapping[str, Any], *, season: CompiledSeason | None = None) -> str:
    normalized = season.validate_conjecture(conjecture) if season is not None else validate_conjecture(conjecture)
    return _canonical_json(
        {
            "claim_kind": normalized.get("claim_kind", "sufficient"),
            "if": normalized["if"],
            "then": normalized["then"],
        }
    )


def _command_board(command: Mapping[str, Any]) -> tuple[str, ...] | None:
    before = command.get("before") or command.get("board")
    if before is None and isinstance(command.get("transition"), Mapping):
        before = command["transition"].get("before")
    if isinstance(before, list) and all(isinstance(row, str) for row in before):
        return tuple(before)
    return None


def _verdict_witness_id(verdict: Verdict) -> str | None:
    details = verdict.details or {}
    before = details.get("before")
    if before is None:
        counterexample = details.get("counterexample")
        if isinstance(counterexample, Mapping):
            before = counterexample.get("board")
            cell = counterexample.get("cell")
            expected = counterexample.get("expected")
            actual = counterexample.get("actual")
        else:
            cell = expected = actual = None
    else:
        cell = details.get("cell")
        expected = details.get("expected")
        actual = details.get("actual")
    if not (
        isinstance(before, list)
        and all(isinstance(row, str) for row in before)
        and isinstance(cell, list)
        and isinstance(expected, str)
        and isinstance(actual, str)
    ):
        return None
    return witness_id(before, cell, expected=expected, actual=actual)


def _strip_transcript_metadata(command: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in command.items() if k != "_meta"}


def _parse_created_at(command: Mapping[str, Any]) -> datetime | None:
    meta = command.get("_meta")
    if meta is None:
        return None
    if not isinstance(meta, Mapping):
        raise ValidationError("_meta must be an object")
    raw = meta.get("created_at")
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValidationError("_meta.created_at must be a string")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError("_meta.created_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _cooldown_identity(command: Mapping[str, Any]) -> str:
    meta = command.get("_meta")
    if isinstance(meta, Mapping):
        author_login = meta.get("author_login")
        if isinstance(author_login, str) and author_login.strip():
            return author_login.strip()
    return _command_player(command)


def _command_player(command: Mapping[str, Any]) -> str:
    if command.get("type") == "conjecture" and isinstance(command.get("conjecture"), Mapping):
        nested = dict(command["conjecture"])
        if "player" not in nested and "player" in command:
            nested["player"] = command["player"]
        return player_name_from_submission(nested)
    return player_name_from_submission(command)


def _check_player_cooldown(
    state: ReplayState,
    command: Mapping[str, Any],
    *,
    min_player_interval_seconds: int,
) -> Verdict | None:
    if min_player_interval_seconds <= 0:
        return None

    created_at = _parse_created_at(command)
    if created_at is None:
        raise ValidationError("cooldown enforcement requires _meta.created_at")

    player = _command_player(command)
    cooldown_identity = _cooldown_identity(command)
    previous = state.last_command_at_by_player.get(cooldown_identity)
    if previous is not None:
        elapsed = (created_at - previous).total_seconds()
        if elapsed < min_player_interval_seconds:
            wait_seconds = int(min_player_interval_seconds - max(0, elapsed))
            return Verdict(
                ok=False,
                kind="invalid",
                player=player,
                message=(
                    f"Player {player!r} moved too soon; wait at least "
                    f"{min_player_interval_seconds} seconds between commands."
                ),
                score_delta=-5,
                details={
                    "reason": "player_cooldown",
                    "cooldown_identity": cooldown_identity,
                    "created_at": created_at.isoformat(),
                    "previous_created_at": previous.isoformat(),
                    "elapsed_seconds": int(elapsed),
                    "required_seconds": min_player_interval_seconds,
                    "wait_seconds": wait_seconds,
                },
            )

    state.last_command_at_by_player[cooldown_identity] = created_at
    return None


def _remember_false_conjecture_counterexample(state: ReplayState, verdict: Verdict) -> None:
    if verdict.kind != "conjecture" or verdict.ok:
        return
    details = verdict.details or {}
    name = details.get("name")
    counterexample = details.get("counterexample")
    if not isinstance(name, str) or not isinstance(counterexample, Mapping):
        return
    board = counterexample.get("board")
    if isinstance(board, list) and all(isinstance(row, str) for row in board):
        state.auto_counterexamples[name] = tuple(board)
    found_witness_id = _verdict_witness_id(verdict)
    if found_witness_id is not None:
        state.auto_counterexample_witness_ids[name] = found_witness_id


def _target_value_for_obligations(obligations: frozenset[str]) -> int:
    return min(30, max(1, len(obligations) // 2048))


def _obligation_counts(obligations: frozenset[str]) -> dict[str, int]:
    summary = summarize_obligation_ids(obligations)
    by_claim_kind = summary["by_claim_kind"]
    return {
        "sufficient": int(by_claim_kind.get("sufficient", 0)),
        "necessary": int(by_claim_kind.get("necessary", 0)),
    }


def _season_adjust_conjecture(
    state: ReplayState,
    verdict: Verdict,
    conjecture: Mapping[str, Any],
    *,
    season: CompiledSeason | None = None,
) -> Verdict:
    _remember_false_conjecture_counterexample(state, verdict)
    if verdict.kind != "conjecture" or not verdict.ok:
        try:
            obligations = obligation_ids_for_conjecture(conjecture, season=season)
        except ValidationError:
            return verdict
        details = verdict.details or {}
        name = details.get("name")
        if isinstance(name, str):
            state.conjecture_target_values[name] = _target_value_for_obligations(obligations)
        return replace(
            verdict,
            details={
                **details,
                "season_potential_obligations": len(obligations),
                "season_potential_obligation_counts": _obligation_counts(obligations),
                "season_target_value": _target_value_for_obligations(obligations),
                "score_components": {
                    "false_conjecture_penalty": verdict.score_delta,
                    "target_value_observed": _target_value_for_obligations(obligations),
                    "final": verdict.score_delta,
                },
            },
        )

    signature = _conjecture_signature(conjecture, season=season)
    if signature in state.conjecture_signatures:
        return Verdict(
            ok=False,
            kind="invalid",
            player=verdict.player,
            message="Duplicate conjecture; season scoring rewards new claims only.",
            score_delta=-2,
            details={
                "reason": "duplicate_conjecture",
                "season_score_basis": "duplicate_conjecture",
                "score_components": {
                    "duplicate_conjecture_penalty": -2,
                    "final": -2,
                },
            },
        )

    obligations = obligation_ids_for_conjecture(conjecture, season=season)
    coverage = state.obligation_ledger.measure(obligations)
    new_counts = _obligation_counts(coverage.new_obligations)
    stale_counts = _obligation_counts(coverage.stale_obligations)
    total_counts = _obligation_counts(coverage.obligations)
    state.conjecture_signatures.add(signature)
    details = verdict.details or {}
    name = details.get("name")
    target_value = _target_value_for_obligations(coverage.obligations)
    if isinstance(name, str):
        state.conjecture_target_values[name] = target_value
    if not coverage.new_obligations:
        adjusted = replace(
            verdict,
            message=f"{verdict.message} Season scoring found no new covered territory.",
            score_delta=0,
            details={
                **details,
                "season_new_obligations": 0,
                "season_new_obligation_counts": new_counts,
                "season_known_obligations": len(coverage.stale_obligations),
                "season_known_obligation_counts": stale_counts,
                "season_total_obligation_counts": total_counts,
                "season_target_value": target_value,
                "season_score_basis": "stale_true_conjecture",
                "season_obligation_examples": sorted(coverage.obligations)[:3],
                "score_components": {
                    "base_law": 10,
                    "new_sufficient_obligations": new_counts["sufficient"],
                    "new_necessary_obligations": new_counts["necessary"],
                    "stale_sufficient_obligations": stale_counts["sufficient"],
                    "stale_necessary_obligations": stale_counts["necessary"],
                    "novelty_bonus": 0,
                    "complexity_penalty": int(details.get("complexity", 0)),
                    "stale_penalty": 10,
                    "final": 0,
                },
            },
        )
        return adjusted

    state.obligation_ledger.mark(coverage)
    complexity = int(details.get("complexity", 0))
    novelty_bonus = min(60, len(coverage.new_obligations) // 512)
    score_delta = max(1, 10 + novelty_bonus - complexity)
    return replace(
        verdict,
        message=f"{verdict.message} Season novelty: {len(coverage.new_obligations)} new obligations.",
        score_delta=score_delta,
        details={
            **details,
            "season_new_obligations": len(coverage.new_obligations),
            "season_new_obligation_counts": new_counts,
            "season_known_obligations": len(coverage.stale_obligations),
            "season_known_obligation_counts": stale_counts,
            "season_total_obligations": len(coverage.obligations),
            "season_total_obligation_counts": total_counts,
            "season_score_basis": "new_obligations",
            "season_novelty_bonus": novelty_bonus,
            "season_target_value": target_value,
            "season_obligation_examples": sorted(coverage.new_obligations)[:3],
            "score_components": {
                "base_law": 10,
                "new_sufficient_obligations": new_counts["sufficient"],
                "new_necessary_obligations": new_counts["necessary"],
                "stale_sufficient_obligations": stale_counts["sufficient"],
                "stale_necessary_obligations": stale_counts["necessary"],
                "novelty_bonus": novelty_bonus,
                "complexity_penalty": complexity,
                "final": score_delta,
            },
        },
    )


def _season_adjust_counterexample(state: ReplayState, verdict: Verdict, command: Mapping[str, Any]) -> Verdict:
    if verdict.kind != "counterexample" or not verdict.ok:
        return verdict

    against = command.get("against")
    if not isinstance(against, str):
        return verdict
    board = _command_board(command)
    details = verdict.details or {}
    minimality_bonus = int(details.get("minimality_bonus", 0))
    found_witness_id = _verdict_witness_id(verdict)
    target_value = state.conjecture_target_values.get(against, 0)

    def components(
        *,
        final: int,
        minimality_bonus_used: int = 0,
        duplicate_penalty: int = 0,
        already_countered_penalty: int = 0,
        verifier_revealed_penalty: int = 0,
    ) -> dict[str, int]:
        return {
            "base_refutation": 15,
            "target_value_observed": target_value,
            "target_value_used": 0,
            "minimality_bonus_available": minimality_bonus,
            "minimality_bonus_used": minimality_bonus_used,
            "duplicate_penalty": duplicate_penalty,
            "already_countered_penalty": already_countered_penalty,
            "verifier_revealed_penalty": verifier_revealed_penalty,
            "final": final,
        }

    if against in state.countered_conjectures:
        if found_witness_id is not None:
            state.known_witness_ids.add(found_witness_id)
        return replace(
            verdict,
            message=f"{verdict.message} Season scoring: this conjecture was already countered.",
            score_delta=1,
            details={
                **details,
                "against": against,
                "season_score_basis": "already_countered",
                "score_components": components(final=1, already_countered_penalty=14),
            },
        )

    state.countered_conjectures.add(against)
    if found_witness_id is not None and found_witness_id in state.known_witness_ids:
        return replace(
            verdict,
            message=f"{verdict.message} Season scoring: this witness pattern is already known.",
            score_delta=2,
            details={
                **details,
                "against": against,
                "season_score_basis": "duplicate_witness",
                "witness_id": found_witness_id,
                "score_components": components(final=2, duplicate_penalty=13),
            },
        )

    if (
        (board is not None and state.auto_counterexamples.get(against) == board)
        or (
            found_witness_id is not None
            and state.auto_counterexample_witness_ids.get(against) == found_witness_id
        )
    ):
        if found_witness_id is not None:
            state.known_witness_ids.add(found_witness_id)
        return replace(
            verdict,
            message=(
                f"{verdict.message} Season scoring: this matches the verifier-revealed "
                "counterexample, so it receives a small first-refutation score."
            ),
            score_delta=5,
            details={
                **details,
                "against": against,
                "season_score_basis": "verifier_revealed_counterexample",
                "witness_id": found_witness_id,
                "score_components": components(final=5, verifier_revealed_penalty=10),
            },
        )

    if found_witness_id is not None:
        state.known_witness_ids.add(found_witness_id)
    return replace(
        verdict,
        score_delta=15 + minimality_bonus,
        details={
            **details,
            "against": against,
            "season_score_basis": "novel_first_counterexample",
            "witness_id": found_witness_id,
            "score_components": components(final=15 + minimality_bonus, minimality_bonus_used=minimality_bonus),
        },
    )


def _apply_verdict(
    state: ReplayState,
    command: Mapping[str, Any],
    verdict: Verdict,
    *,
    season_scoring: bool,
    conjecture: Mapping[str, Any] | None = None,
    season: CompiledSeason | None = None,
) -> Verdict:
    adjusted = verdict
    if season_scoring and conjecture is not None:
        adjusted = _season_adjust_conjecture(state, adjusted, conjecture, season=season)
    elif season_scoring:
        _remember_false_conjecture_counterexample(state, adjusted)
        adjusted = _season_adjust_counterexample(state, adjusted, command)
    state.apply(adjusted)
    return adjusted


def apply_command(
    state: ReplayState,
    command: Mapping[str, Any],
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = False,
    season: CompiledSeason | None = None,
) -> Verdict:
    try:
        command = normalize_command(command)
        cooldown_verdict = _check_player_cooldown(
            state,
            command,
            min_player_interval_seconds=min_player_interval_seconds,
        )
        if cooldown_verdict is not None:
            state.apply(cooldown_verdict)
            return cooldown_verdict
        command = _strip_transcript_metadata(command)
        command_type = command["type"]

        if command_type == "hello":
            hello = validate_hello_command(command)
            state.agent_profiles[hello["player"]] = hello["agent_profile"]
            verdict = Verdict(
                ok=True,
                kind="hello",
                player=hello["player"],
                message=f"Registered self-reported agent profile for {hello['player']!r}.",
                score_delta=0,
                details={"agent_profile": hello["agent_profile"]},
            )
            return _apply_verdict(state, hello, verdict, season_scoring=season_scoring, season=season)

        if command_type == "conjecture":
            if "conjecture" in command:
                conjecture = dict(command["conjecture"])
                if "player" not in conjecture and "player" in command:
                    conjecture["player"] = command["player"]
            else:
                conjecture = {k: v for k, v in command.items() if k != "type"}
            normalized = season.validate_conjecture(conjecture) if season is not None else validate_conjecture(conjecture)
            # Store every well-formed conjecture, even if the verifier can already
            # refute it. This makes the public transcript meaningful: other agents
            # may still earn points by submitting compact counterexamples against
            # a flawed conjecture. Invalid-schema conjectures are not stored.
            verdict = verify_conjecture(normalized, season=season)
            state.conjectures[normalized["name"]] = normalized
            return _apply_verdict(state, command, verdict, season_scoring=season_scoring, conjecture=normalized, season=season)

        if command_type == "counterexample":
            against = command.get("against")
            if not isinstance(against, str) or not against:
                raise ValidationError("counterexample needs non-empty 'against'")
            if against not in state.conjectures:
                raise ValidationError(f"unknown conjecture: {against}")
            before = command.get("before") or command.get("board")
            if before is None and isinstance(command.get("transition"), Mapping):
                before = command["transition"].get("before")
            if before is None:
                raise ValidationError("counterexample needs before/board")
            conjecture = dict(state.conjectures[against])
            # The counterexample finder, not the conjecture author, receives score.
            if "player" in command:
                conjecture["player"] = player_name_from_submission(command)
            verdict = check_counterexample(conjecture, before, season=season)
            return _apply_verdict(state, command, verdict, season_scoring=season_scoring, season=season)

        if command_type == "score":
            rows = leaderboard_rows(state.scores)
            verdict = Verdict(
                ok=True,
                kind="score",
                player=player_name_from_submission(command),
                message="Scoreboard rendered.",
                score_delta=0,
                details={"leaderboard": rows, "agent_profiles": dict(state.agent_profiles)},
            )
            return _apply_verdict(state, command, verdict, season_scoring=season_scoring, season=season)

        if command_type == "invalid":
            verdict = Verdict(
                ok=False,
                kind="invalid",
                player=player_name_from_submission(command),
                message=str(command.get("message") or command.get("_error") or "Invalid command."),
                score_delta=-5,
                details={"reason": command.get("reason", "invalid_command")},
            )
            return _apply_verdict(state, command, verdict, season_scoring=season_scoring, season=season)

        raise AssertionError("unreachable")
    except ValidationError as exc:
        verdict = Verdict(ok=False, kind="invalid", message=str(exc), player=player_name_from_submission(command), score_delta=-5)
        state.apply(verdict)
        return verdict


def iter_jsonl(path: str | Path) -> Iterable[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"invalid JSON on line {line_no}: {exc.msg}") from exc
            if not isinstance(payload, dict):
                raise ValidationError(f"line {line_no} must be a JSON object")
            yield payload


def replay_records(
    records: Iterable[Mapping[str, Any]],
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = False,
    season: CompiledSeason | None = None,
) -> ReplayState:
    state = ReplayState()
    for record in records:
        apply_command(
            state,
            record,
            min_player_interval_seconds=min_player_interval_seconds,
            season_scoring=season_scoring,
            season=season,
        )
    return state


def replay_file(
    path: str | Path,
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = False,
    season: CompiledSeason | None = None,
) -> ReplayState:
    return replay_records(
        iter_jsonl(path),
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=season,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a Conjecture Golf transcript.")
    parser.add_argument("path", help="JSONL transcript path")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown leaderboard")
    parser.add_argument(
        "--min-player-interval-seconds",
        type=int,
        default=0,
        help="Reject commands from the same player submitted sooner than this many seconds apart.",
    )
    parser.add_argument("--season-scoring", action="store_true", help="Reward only novel season progress.")
    parser.add_argument("--season", help="Optional data-only season spec path")
    args = parser.parse_args(argv)
    season = load_optional_compiled_season(args.season)
    state = replay_file(
        args.path,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=args.season_scoring,
        season=season,
    )
    rows = leaderboard_rows(state.scores)
    if args.json:
        print(
            json.dumps(
                {
                    "leaderboard": rows,
                    "agent_profiles": state.agent_profiles,
                    "verdicts": [v.to_dict() for v in state.verdicts],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render_markdown(rows))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
