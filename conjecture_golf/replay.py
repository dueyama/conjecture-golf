"""Replay transcripts for Conjecture Golf.

A transcript is a JSONL file. Each line is one public command. Replaying the
same transcript must always produce the same final score.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .dsl import player_name_from_submission, validate_conjecture
from .score import PlayerScore, apply_verdict, leaderboard_rows, render_markdown
from .verify import Verdict, check_counterexample, verify_conjecture
from .world import ValidationError


@dataclass
class ReplayState:
    conjectures: dict[str, dict[str, Any]] = field(default_factory=dict)
    scores: dict[str, PlayerScore] = field(default_factory=dict)
    verdicts: list[Verdict] = field(default_factory=list)

    def apply(self, verdict: Verdict) -> None:
        self.verdicts.append(verdict)
        apply_verdict(self.scores, verdict)


def normalize_command(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ValidationError("transcript record must be an object")
    command_type = record.get("type")
    if command_type not in {"conjecture", "counterexample", "score"}:
        raise ValidationError("record type must be conjecture, counterexample, or score")
    return dict(record)


def apply_command(state: ReplayState, command: Mapping[str, Any]) -> Verdict:
    try:
        command = normalize_command(command)
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
            state.apply(verdict)
            return verdict

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
            state.apply(verdict)
            return verdict

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
            state.apply(verdict)
            return verdict

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


def replay_records(records: Iterable[Mapping[str, Any]]) -> ReplayState:
    state = ReplayState()
    for record in records:
        apply_command(state, record)
    return state


def replay_file(path: str | Path) -> ReplayState:
    return replay_records(iter_jsonl(path))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a Conjecture Golf transcript.")
    parser.add_argument("path", help="JSONL transcript path")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown leaderboard")
    args = parser.parse_args(argv)
    state = replay_file(args.path)
    rows = leaderboard_rows(state.scores)
    if args.json:
        print(json.dumps({"leaderboard": rows, "verdicts": [v.to_dict() for v in state.verdicts]}, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(rows))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
