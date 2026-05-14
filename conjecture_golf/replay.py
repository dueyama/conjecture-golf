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

from .dsl import player_name_from_submission, validate_conjecture
from .canonical import witness_id
from .obligations import ObligationLedger, obligation_ids_for_conjecture
from .score import PlayerScore, apply_verdict, leaderboard_rows, render_markdown
from .verify import Verdict, check_counterexample, verify_conjecture
from .world import ValidationError


@dataclass
class ReplayState:
    conjectures: dict[str, dict[str, Any]] = field(default_factory=dict)
    scores: dict[str, PlayerScore] = field(default_factory=dict)
    verdicts: list[Verdict] = field(default_factory=list)
    last_command_at_by_player: dict[str, datetime] = field(default_factory=dict)
    obligation_ledger: ObligationLedger = field(default_factory=ObligationLedger)
    conjecture_signatures: set[str] = field(default_factory=set)
    auto_counterexamples: dict[str, tuple[str, ...]] = field(default_factory=dict)
    auto_counterexample_witness_ids: dict[str, str] = field(default_factory=dict)
    known_witness_ids: set[str] = field(default_factory=set)
    countered_conjectures: set[str] = field(default_factory=set)

    def apply(self, verdict: Verdict) -> None:
        self.verdicts.append(verdict)
        apply_verdict(self.scores, verdict)


def normalize_command(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ValidationError("transcript record must be an object")
    command_type = record.get("type")
    if command_type not in {"conjecture", "counterexample", "score", "invalid"}:
        raise ValidationError("record type must be conjecture, counterexample, score, or invalid")
    return dict(record)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _conjecture_signature(conjecture: Mapping[str, Any]) -> str:
    normalized = validate_conjecture(conjecture)
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


def _season_adjust_conjecture(state: ReplayState, verdict: Verdict, conjecture: Mapping[str, Any]) -> Verdict:
    _remember_false_conjecture_counterexample(state, verdict)
    if verdict.kind != "conjecture" or not verdict.ok:
        return verdict

    signature = _conjecture_signature(conjecture)
    if signature in state.conjecture_signatures:
        return Verdict(
            ok=False,
            kind="invalid",
            player=verdict.player,
            message="Duplicate conjecture; season scoring rewards new claims only.",
            score_delta=-2,
            details={"reason": "duplicate_conjecture"},
        )

    obligations = obligation_ids_for_conjecture(conjecture)
    coverage = state.obligation_ledger.measure(obligations)
    state.conjecture_signatures.add(signature)
    if not coverage.new_obligations:
        adjusted = replace(
            verdict,
            message=f"{verdict.message} Season scoring found no new covered territory.",
            score_delta=0,
            details={
                **(verdict.details or {}),
                "season_new_obligations": 0,
                "season_known_obligations": len(coverage.stale_obligations),
                "season_score_basis": "stale_true_conjecture",
                "season_obligation_examples": sorted(coverage.obligations)[:3],
            },
        )
        return adjusted

    state.obligation_ledger.mark(coverage)
    details = verdict.details or {}
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
            "season_known_obligations": len(coverage.stale_obligations),
            "season_total_obligations": len(coverage.obligations),
            "season_score_basis": "new_obligations",
            "season_novelty_bonus": novelty_bonus,
            "season_obligation_examples": sorted(coverage.new_obligations)[:3],
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

    if against in state.countered_conjectures:
        if found_witness_id is not None:
            state.known_witness_ids.add(found_witness_id)
        return replace(
            verdict,
            message=f"{verdict.message} Season scoring: this conjecture was already countered.",
            score_delta=1,
            details={**details, "season_score_basis": "already_countered"},
        )

    state.countered_conjectures.add(against)
    if found_witness_id is not None and found_witness_id in state.known_witness_ids:
        return replace(
            verdict,
            message=f"{verdict.message} Season scoring: this witness pattern is already known.",
            score_delta=2,
            details={**details, "season_score_basis": "duplicate_witness", "witness_id": found_witness_id},
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
                "season_score_basis": "verifier_revealed_counterexample",
                "witness_id": found_witness_id,
            },
        )

    if found_witness_id is not None:
        state.known_witness_ids.add(found_witness_id)
    return replace(
        verdict,
        score_delta=15 + minimality_bonus,
        details={**details, "season_score_basis": "novel_first_counterexample", "witness_id": found_witness_id},
    )


def _apply_verdict(
    state: ReplayState,
    command: Mapping[str, Any],
    verdict: Verdict,
    *,
    season_scoring: bool,
    conjecture: Mapping[str, Any] | None = None,
) -> Verdict:
    adjusted = verdict
    if season_scoring and conjecture is not None:
        adjusted = _season_adjust_conjecture(state, adjusted, conjecture)
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

        if command_type == "conjecture":
            if "conjecture" in command:
                conjecture = dict(command["conjecture"])
                if "player" not in conjecture and "player" in command:
                    conjecture["player"] = command["player"]
            else:
                conjecture = {k: v for k, v in command.items() if k != "type"}
            normalized = validate_conjecture(conjecture)
            # Store every well-formed conjecture, even if the verifier can already
            # refute it. This makes the public transcript meaningful: other agents
            # may still earn points by submitting compact counterexamples against
            # a flawed conjecture. Invalid-schema conjectures are not stored.
            verdict = verify_conjecture(normalized)
            state.conjectures[normalized["name"]] = normalized
            return _apply_verdict(state, command, verdict, season_scoring=season_scoring, conjecture=normalized)

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
            verdict = check_counterexample(conjecture, before)
            return _apply_verdict(state, command, verdict, season_scoring=season_scoring)

        if command_type == "score":
            rows = leaderboard_rows(state.scores)
            verdict = Verdict(
                ok=True,
                kind="score",
                player=player_name_from_submission(command),
                message="Scoreboard rendered.",
                score_delta=0,
                details={"leaderboard": rows},
            )
            return _apply_verdict(state, command, verdict, season_scoring=season_scoring)

        if command_type == "invalid":
            verdict = Verdict(
                ok=False,
                kind="invalid",
                player=player_name_from_submission(command),
                message=str(command.get("message") or command.get("_error") or "Invalid command."),
                score_delta=-5,
                details={"reason": command.get("reason", "invalid_command")},
            )
            return _apply_verdict(state, command, verdict, season_scoring=season_scoring)

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
) -> ReplayState:
    state = ReplayState()
    for record in records:
        apply_command(
            state,
            record,
            min_player_interval_seconds=min_player_interval_seconds,
            season_scoring=season_scoring,
        )
    return state


def replay_file(
    path: str | Path,
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = False,
) -> ReplayState:
    return replay_records(
        iter_jsonl(path),
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
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
    args = parser.parse_args(argv)
    state = replay_file(
        args.path,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=args.season_scoring,
    )
    rows = leaderboard_rows(state.scores)
    if args.json:
        print(json.dumps({"leaderboard": rows, "verdicts": [v.to_dict() for v in state.verdicts]}, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(rows))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
