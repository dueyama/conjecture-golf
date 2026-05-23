"""Inspect raw chat responses from external AI participants.

The game contract still requires exactly one JSON object and no prose. This
module helps operators preserve that boundary when a chat-only participant
returns Markdown fences or explanatory text.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .dsl import player_name_from_submission
from .world import ValidationError


def _read_text(path: str | Path) -> str:
    if str(path) == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _json_object_spans(text: str) -> list[tuple[int, int, dict[str, Any]]]:
    decoder = json.JSONDecoder()
    spans: list[tuple[int, int, dict[str, Any]]] = []
    index = 0
    while True:
        start = text.find("{", index)
        if start == -1:
            return spans
        try:
            payload, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(payload, dict):
            spans.append((start, end, payload))
        index = max(end, start + 1)


def _has_markdown_fence(text: str) -> bool:
    return "```" in text


def _strict_json_object(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _command_player(command: Mapping[str, Any]) -> str:
    if command.get("type") == "conjecture" and isinstance(command.get("conjecture"), Mapping):
        nested = dict(command["conjecture"])
        if "player" not in nested and "player" in command:
            nested["player"] = command["player"]
        return player_name_from_submission(nested)
    return player_name_from_submission(command)


def inspect_chat_response(text: str, *, expected_player: str | None = None) -> dict[str, Any]:
    """Inspect a raw response and return a deterministic extraction report."""

    strict_payload = _strict_json_object(text)
    spans = _json_object_spans(text)
    violations: list[str] = []
    if _has_markdown_fence(text):
        violations.append("markdown_fence")

    payload: dict[str, Any] | None = None
    status = "no_json_object"
    if strict_payload is not None:
        payload = strict_payload
        status = "strict_json"
    elif len(spans) == 1:
        start, end, extracted = spans[0]
        payload = extracted
        before = text[:start].strip()
        after = text[end:].strip()
        if before or after:
            violations.append("prose_outside_json")
        status = "extracted_json_with_contract_violation"
    elif len(spans) > 1:
        status = "multiple_json_objects"
        violations.append("multiple_json_objects")

    player = _command_player(payload) if payload is not None else None
    player_matches_expected = None
    if expected_player is not None:
        player_matches_expected = player == expected_player
        if payload is not None and not player_matches_expected:
            violations.append("player_mismatch")
            status = "player_mismatch"

    contract_ok = payload is not None and status == "strict_json" and not violations
    return {
        "contract_ok": contract_ok,
        "extracted": payload,
        "expected_player": expected_player,
        "json_objects_found": len(spans),
        "player": player,
        "player_matches_expected": player_matches_expected,
        "status": status,
        "violations": violations,
    }


def can_write_extracted_move(report: Mapping[str, Any], *, allow_extraction: bool = False) -> bool:
    payload = report.get("extracted")
    player_ok = report.get("player_matches_expected") is not False
    return bool(payload) and (
        report.get("contract_ok") is True
        or (
            allow_extraction
            and player_ok
            and report.get("status") not in {"multiple_json_objects", "player_mismatch"}
        )
    )


def write_extracted_move(path: str | Path, payload: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect a raw external-AI chat response for one JSON move.")
    parser.add_argument("response", help="Raw response text path, or '-' for stdin")
    parser.add_argument("--expected-player", help="Require extracted move player to match this player")
    parser.add_argument("--out", help="Write extracted JSON object here when accepted")
    parser.add_argument(
        "--allow-extraction",
        action="store_true",
        help="Permit writing a single JSON object even when prose or Markdown fences violate the contract.",
    )
    parser.add_argument("--report", help="Write the inspection report JSON here")
    parser.add_argument("--json", action="store_true", help="Print JSON report instead of Markdown")
    args = parser.parse_args(argv)

    report = inspect_chat_response(_read_text(args.response), expected_player=args.expected_player)
    payload = report["extracted"]
    can_write = can_write_extracted_move(report, allow_extraction=args.allow_extraction)
    if args.out and can_write:
        write_extracted_move(args.out, payload)
    if args.report:
        write_extracted_move(args.report, report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_report_markdown(report))

    if not payload:
        return 1
    if report["contract_ok"]:
        return 0
    return 0 if args.allow_extraction and can_write else 2


def render_report_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Chat Response Inspection",
        "",
        f"Contract OK: `{str(report['contract_ok']).lower()}`",
        f"Status: `{report['status']}`",
        f"JSON objects found: `{report['json_objects_found']}`",
        f"Player: `{report.get('player')}`",
    ]
    if report.get("expected_player") is not None:
        lines.append(f"Expected player: `{report['expected_player']}`")
        lines.append(f"Player match: `{str(report['player_matches_expected']).lower()}`")
    violations = report.get("violations") or []
    if violations:
        lines.extend(["", "## Contract Violations", ""])
        lines.extend(f"- `{item}`" for item in violations)
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
