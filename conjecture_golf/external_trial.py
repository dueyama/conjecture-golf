"""Preflight checks for a generated external-AI trial kit.

This module inspects match-pack metadata before prompts are sent to external
chat-only participants. It treats every file as data and never executes
participant text.
"""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


REQUIRED_TRIAL_FILES = {
    "manifest.json",
    "transcript.jsonl",
    "external_trial/README.md",
    "external_trial/collection_status.json",
    "external_trial/participant_roster.json",
    "external_trial/expected_responses.json",
    "external_trial/raw_responses/README.md",
}

EXPECTED_RESPONSE_KEYS = {
    "player",
    "strategy",
    "copy_paste_prompt",
    "participant_prompt",
    "raw_response",
    "response_report",
}

COLLECTION_STATUS_VALUES = {"not_sent", "sent", "received", "withdrawn"}
COLLECTION_STATUS_KEYS = {
    "player",
    "status",
    "prompt_sent",
    "raw_response",
    "prompt_sent_at",
    "response_received_at",
    "operator_notes",
}


@dataclass(frozen=True)
class ExternalTrialCheck:
    key: str
    passed: bool
    category: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "passed": self.passed,
            "category": self.category,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ExternalTrialReport:
    pack_dir: str
    passed: bool
    response_count: int
    expected_players: list[str]
    checks: list[ExternalTrialCheck]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_dir": self.pack_dir,
            "passed": self.passed,
            "response_count": self.response_count,
            "expected_players": self.expected_players,
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class ExternalTrialStatusReport:
    pack_dir: str
    passed: bool
    ready_for_raw_round: bool
    response_count: int
    ready_players: list[str]
    waiting_players: list[str]
    checks: list[ExternalTrialCheck]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_dir": self.pack_dir,
            "passed": self.passed,
            "ready_for_raw_round": self.ready_for_raw_round,
            "response_count": self.response_count,
            "ready_players": self.ready_players,
            "waiting_players": self.waiting_players,
            "checks": [check.to_dict() for check in self.checks],
        }


def _check(key: str, passed: bool, *, category: str, evidence: str) -> ExternalTrialCheck:
    return ExternalTrialCheck(key=key, passed=bool(passed), category=category, evidence=evidence)


def _safe_relative_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        return None
    posix = PurePosixPath(value)
    if posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
        return None
    return Path(*posix.parts)


def _path_exists(root: Path, value: Any) -> bool:
    relative = _safe_relative_path(value)
    return relative is not None and (root / relative).exists()


def _load_json(root: Path, relative: str) -> tuple[Any | None, str | None]:
    path = root / relative
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except FileNotFoundError:
        return None, f"missing file: {relative}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON in {relative}: {exc.msg}"


def _player_entries_by_name(roster: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    if not isinstance(roster, dict):
        return {}, ["participant_roster.json must be a JSON object"]
    participants = roster.get("participants")
    if not isinstance(participants, list):
        return {}, ["participant_roster.json must contain a participants list"]

    entries: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(participants, start=1):
        if not isinstance(item, dict):
            errors.append(f"participant {index} must be an object")
            continue
        player = str(item.get("player", "")).strip()
        if not player:
            errors.append(f"participant {index} is missing player")
            continue
        if player in entries:
            errors.append(f"duplicate participant player: {player}")
            continue
        entries[player] = item
    return entries, errors


def _collection_entries_by_name(payload: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {}, ["collection_status.json must be a JSON object"]
    if payload.get("schema") != "conjecture_golf.external_trial_status.v1":
        errors.append("collection_status.json has unsupported schema")
    participants = payload.get("participants")
    if not isinstance(participants, list):
        return {}, errors + ["collection_status.json must contain a participants list"]

    entries: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(participants, start=1):
        if not isinstance(item, dict):
            errors.append(f"collection participant {index} must be an object")
            continue
        unknown = sorted(set(item) - COLLECTION_STATUS_KEYS)
        missing = sorted(COLLECTION_STATUS_KEYS - set(item))
        if unknown:
            errors.append(f"collection participant {index} has unknown fields: {', '.join(unknown)}")
        if missing:
            errors.append(f"collection participant {index} missing fields: {', '.join(missing)}")
        player = str(item.get("player", "")).strip()
        if not player:
            errors.append(f"collection participant {index} is missing player")
            continue
        if player in entries:
            errors.append(f"duplicate collection participant player: {player}")
            continue
        status = str(item.get("status", "")).strip()
        if status not in COLLECTION_STATUS_VALUES:
            errors.append(f"{player}: invalid collection status {status!r}")
        entries[player] = item
    return entries, errors


def _expected_response_entries(expected: Any) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if not isinstance(expected, dict):
        return [], ["expected_responses.json must be a JSON object"]
    responses = expected.get("responses")
    if not isinstance(responses, list):
        return [], ["expected_responses.json must contain a responses list"]

    entries: list[dict[str, Any]] = []
    players: set[str] = set()
    raw_paths: set[str] = set()
    for index, item in enumerate(responses, start=1):
        if not isinstance(item, dict):
            errors.append(f"response {index} must be an object")
            continue
        missing = sorted(EXPECTED_RESPONSE_KEYS - set(item))
        unknown = sorted(set(item) - EXPECTED_RESPONSE_KEYS)
        if missing:
            errors.append(f"response {index} missing fields: {', '.join(missing)}")
        if unknown:
            errors.append(f"response {index} has unknown fields: {', '.join(unknown)}")

        player = str(item.get("player", "")).strip()
        if not player:
            errors.append(f"response {index} is missing player")
        elif player in players:
            errors.append(f"duplicate response player: {player}")
        players.add(player)

        raw_response = str(item.get("raw_response", "")).strip()
        if raw_response in raw_paths:
            errors.append(f"duplicate raw response path: {raw_response}")
        raw_paths.add(raw_response)

        entries.append(dict(item, player=player))
    return entries, errors


def _model_identity(entry: Mapping[str, Any]) -> str:
    return str(entry.get("model") or entry.get("model_name") or entry.get("model_family") or "").strip()


def _raw_response_path_ok(path: Any) -> bool:
    relative = _safe_relative_path(path)
    if relative is None:
        return False
    parts = relative.parts
    return (
        len(parts) == 3
        and parts[0] == "external_trial"
        and parts[1] == "raw_responses"
        and relative.suffix == ".txt"
    )


def _contains_ordered_tokens(command: str, required: list[str]) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    search_at = 0
    for required_token in required:
        try:
            index = tokens.index(required_token, search_at)
        except ValueError:
            return False
        search_at = index + 1
    return True


def inspect_external_trial(
    pack_dir: str | Path,
    *,
    allow_existing_responses: bool = False,
) -> ExternalTrialReport:
    root = Path(pack_dir)
    checks: list[ExternalTrialCheck] = []

    root_is_dir = root.exists() and root.is_dir()
    checks.append(
        _check(
            "match_pack_directory_exists",
            root_is_dir,
            category="structure",
            evidence=f"match pack directory: {root}",
        )
    )
    if not root_is_dir:
        return ExternalTrialReport(
            pack_dir=str(root),
            passed=False,
            response_count=0,
            expected_players=[],
            checks=checks,
        )

    missing = sorted(relative for relative in REQUIRED_TRIAL_FILES if not (root / relative).exists())
    checks.append(
        _check(
            "required_external_trial_files_exist",
            not missing,
            category="structure",
            evidence="all required files are present" if not missing else f"missing: {', '.join(missing)}",
        )
    )

    manifest, manifest_error = _load_json(root, "manifest.json")
    checks.append(
        _check(
            "manifest_json_valid",
            manifest_error is None and isinstance(manifest, dict),
            category="structure",
            evidence=manifest_error or "manifest.json is a JSON object",
        )
    )
    trial_manifest = manifest.get("external_trial") if isinstance(manifest, dict) else None
    checks.append(
        _check(
            "manifest_declares_external_trial",
            isinstance(trial_manifest, dict),
            category="structure",
            evidence="manifest has external_trial metadata"
            if isinstance(trial_manifest, dict)
            else "manifest missing external_trial metadata",
        )
    )
    manifest_files = (
        {item for item in manifest.get("files", []) if isinstance(item, str)}
        if isinstance(manifest, dict) and isinstance(manifest.get("files"), list)
        else set()
    )
    manifest_missing = sorted(REQUIRED_TRIAL_FILES - manifest_files)
    checks.append(
        _check(
            "manifest_lists_external_trial_files",
            not manifest_missing,
            category="structure",
            evidence="manifest lists required external trial files"
            if not manifest_missing
            else f"manifest missing file entries: {', '.join(manifest_missing)}",
        )
    )

    expected, expected_error = _load_json(root, "external_trial/expected_responses.json")
    roster, roster_error = _load_json(root, "external_trial/participant_roster.json")
    checks.append(
        _check(
            "expected_responses_json_valid",
            expected_error is None,
            category="schema",
            evidence=expected_error or "expected_responses.json parsed",
        )
    )
    checks.append(
        _check(
            "participant_roster_json_valid",
            roster_error is None,
            category="schema",
            evidence=roster_error or "participant_roster.json parsed",
        )
    )

    response_entries, response_errors = _expected_response_entries(expected)
    checks.append(
        _check(
            "expected_responses_schema",
            not response_errors,
            category="schema",
            evidence="expected response entries match schema"
            if not response_errors
            else "; ".join(response_errors[:6]),
        )
    )
    checks.append(
        _check(
            "expected_responses_present",
            len(response_entries) > 0,
            category="participants",
            evidence=f"{len(response_entries)} external response slots",
        )
    )

    roster_entries, roster_errors = _player_entries_by_name(roster)
    checks.append(
        _check(
            "participant_roster_schema",
            not roster_errors,
            category="schema",
            evidence="participant roster entries are keyed by player"
            if not roster_errors
            else "; ".join(roster_errors[:6]),
        )
    )

    expected_players = sorted(entry["player"] for entry in response_entries if entry["player"])
    roster_players = sorted(roster_entries)
    checks.append(
        _check(
            "roster_players_match_expected_responses",
            expected_players == roster_players,
            category="participants",
            evidence=f"expected={expected_players} roster={roster_players}",
        )
    )

    prompt_path_errors: list[str] = []
    raw_path_errors: list[str] = []
    roster_errors = []
    prompt_map_errors: list[str] = []
    raw_response_paths: list[str] = []
    for entry in response_entries:
        player = entry["player"]
        for key in ("copy_paste_prompt", "participant_prompt"):
            if not _path_exists(root, entry.get(key)):
                prompt_path_errors.append(f"{player}:{key}={entry.get(key)!r}")
        raw_response = str(entry.get("raw_response", "")).strip()
        raw_response_paths.append(raw_response)
        if not _raw_response_path_ok(raw_response):
            raw_path_errors.append(f"{player}:raw_response={raw_response!r}")
        raw_relative = _safe_relative_path(raw_response)
        if raw_relative is not None:
            prompt_map = Path("external_trial") / "prompt_map" / f"{raw_relative.stem}.md"
            if not (root / prompt_map).exists():
                prompt_map_errors.append(f"{player}:{prompt_map.as_posix()}")

        roster_entry = roster_entries.get(player)
        if roster_entry is None:
            continue
        if roster_entry.get("external") is not True:
            roster_errors.append(f"{player}: external must be true")
        if str(roster_entry.get("strategy", "")).strip() != str(entry.get("strategy", "")).strip():
            roster_errors.append(f"{player}: strategy mismatch")
        if str(roster_entry.get("prompt_sent", "")).strip() != str(entry.get("copy_paste_prompt", "")).strip():
            roster_errors.append(f"{player}: prompt_sent mismatch")
        if str(roster_entry.get("raw_response", "")).strip() != raw_response:
            roster_errors.append(f"{player}: raw_response mismatch")

    checks.append(
        _check(
            "expected_prompt_paths_exist",
            not prompt_path_errors,
            category="structure",
            evidence="all copy-paste and participant prompt paths exist"
            if not prompt_path_errors
            else "; ".join(prompt_path_errors[:6]),
        )
    )
    checks.append(
        _check(
            "raw_response_paths_are_safe_and_unique",
            not raw_path_errors and len(raw_response_paths) == len(set(raw_response_paths)),
            category="security",
            evidence="raw response paths are unique .txt files under external_trial/raw_responses"
            if not raw_path_errors and len(raw_response_paths) == len(set(raw_response_paths))
            else "; ".join(raw_path_errors[:6]) or "duplicate raw response paths",
        )
    )
    checks.append(
        _check(
            "prompt_map_files_exist",
            not prompt_map_errors,
            category="structure",
            evidence="prompt_map contains one operator card per response"
            if not prompt_map_errors
            else "; ".join(prompt_map_errors[:6]),
        )
    )
    checks.append(
        _check(
            "roster_entries_match_expected_responses",
            not roster_errors,
            category="participants",
            evidence="roster entries match expected response prompts, paths, strategies, and external flags"
            if not roster_errors
            else "; ".join(roster_errors[:6]),
        )
    )

    raw_dir = root / "external_trial" / "raw_responses"
    existing_txt = sorted(path.name for path in raw_dir.glob("*.txt")) if raw_dir.exists() else []
    expected_names = sorted(Path(path).name for path in raw_response_paths if _raw_response_path_ok(path))
    unexpected_txt = sorted(set(existing_txt) - set(expected_names))
    if allow_existing_responses:
        existing_ok = not unexpected_txt
        evidence = (
            "existing raw responses are limited to expected filenames"
            if existing_ok
            else f"unexpected raw response files: {', '.join(unexpected_txt)}"
        )
    else:
        existing_ok = not existing_txt
        evidence = (
            "raw response directory is empty before sending prompts"
            if existing_ok
            else f"raw responses already exist before send: {', '.join(existing_txt)}"
        )
    checks.append(
        _check(
            "raw_responses_empty_before_send",
            existing_ok,
            category="security",
            evidence=evidence,
        )
    )

    readme_path = root / "external_trial" / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""
    checks.append(
        _check(
            "external_trial_readme_advertises_preflight_and_final_gate",
            "trial-preflight" in readme_text and "--final-external-evidence" in readme_text,
            category="operator_flow",
            evidence="README includes trial-preflight and final evidence handoff"
            if "trial-preflight" in readme_text and "--final-external-evidence" in readme_text
            else "README must mention trial-preflight and --final-external-evidence",
        )
    )

    command = ""
    if isinstance(trial_manifest, dict):
        command = str(trial_manifest.get("raw_round_command", ""))
    command_ok = _contains_ordered_tokens(
        command,
        [
            "python",
            "-m",
            "conjecture_golf.season0",
            "raw-round",
            "transcript.jsonl",
            "external_trial/raw_responses",
            "--out",
            "external_trial/round",
            "--participant-roster",
            "external_trial/participant_roster.json",
            "--strict-exit",
        ],
    )
    checks.append(
        _check(
            "raw_round_command_is_reproducible",
            command_ok,
            category="operator_flow",
            evidence="manifest raw_round_command uses transcript, raw_responses, roster, and strict exit"
            if command_ok
            else "manifest raw_round_command is missing required raw-round tokens",
        )
    )

    passed = all(check.passed for check in checks)
    return ExternalTrialReport(
        pack_dir=str(root),
        passed=passed,
        response_count=len(response_entries),
        expected_players=expected_players,
        checks=checks,
    )


def inspect_external_trial_status(pack_dir: str | Path) -> ExternalTrialStatusReport:
    root = Path(pack_dir)
    checks: list[ExternalTrialCheck] = []

    root_is_dir = root.exists() and root.is_dir()
    checks.append(
        _check(
            "match_pack_directory_exists",
            root_is_dir,
            category="structure",
            evidence=f"match pack directory: {root}",
        )
    )
    if not root_is_dir:
        return ExternalTrialStatusReport(
            pack_dir=str(root),
            passed=False,
            ready_for_raw_round=False,
            response_count=0,
            ready_players=[],
            waiting_players=[],
            checks=checks,
        )

    expected, expected_error = _load_json(root, "external_trial/expected_responses.json")
    roster, roster_error = _load_json(root, "external_trial/participant_roster.json")
    collection, collection_error = _load_json(root, "external_trial/collection_status.json")
    checks.append(
        _check(
            "status_inputs_parse",
            not any([expected_error, roster_error, collection_error]),
            category="schema",
            evidence="expected_responses, participant_roster, and collection_status parsed"
            if not any([expected_error, roster_error, collection_error])
            else "; ".join(error for error in [expected_error, roster_error, collection_error] if error),
        )
    )

    response_entries, response_errors = _expected_response_entries(expected)
    roster_entries, roster_errors = _player_entries_by_name(roster)
    collection_entries, collection_errors = _collection_entries_by_name(collection)
    checks.append(
        _check(
            "collection_status_schema",
            not collection_errors,
            category="schema",
            evidence="collection status entries match schema"
            if not collection_errors
            else "; ".join(collection_errors[:8]),
        )
    )

    expected_by_player = {entry["player"]: entry for entry in response_entries if entry["player"]}
    expected_players = sorted(expected_by_player)
    roster_players = sorted(roster_entries)
    collection_players = sorted(collection_entries)
    checks.append(
        _check(
            "collection_players_match_expected_responses",
            expected_players == roster_players == collection_players,
            category="participants",
            evidence=f"expected={expected_players} roster={roster_players} collection={collection_players}",
        )
    )

    path_errors: list[str] = []
    model_errors: list[str] = []
    received_without_raw: list[str] = []
    raw_without_received: list[str] = []
    ready_players: list[str] = []
    waiting_players: list[str] = []
    for player in expected_players:
        expected_entry = expected_by_player[player]
        collection_entry = collection_entries.get(player, {})
        roster_entry = roster_entries.get(player, {})
        if str(collection_entry.get("prompt_sent", "")).strip() != str(expected_entry.get("copy_paste_prompt", "")).strip():
            path_errors.append(f"{player}: prompt_sent mismatch")
        raw_response = str(expected_entry.get("raw_response", "")).strip()
        if str(collection_entry.get("raw_response", "")).strip() != raw_response:
            path_errors.append(f"{player}: raw_response mismatch")
        raw_relative = _safe_relative_path(raw_response)
        raw_exists = raw_relative is not None and (root / raw_relative).exists()
        status = str(collection_entry.get("status", "")).strip()
        has_model = bool(_model_identity(roster_entry))
        has_interface = bool(str(roster_entry.get("interface", "")).strip())
        if status == "received" and not raw_exists:
            received_without_raw.append(player)
        if raw_exists and status != "received":
            raw_without_received.append(player)
        if raw_exists and status == "received" and has_model and has_interface:
            ready_players.append(player)
        else:
            waiting_players.append(player)
        if raw_exists and status == "received" and not has_model:
            model_errors.append(f"{player}: missing model/model_name/model_family")
        if raw_exists and status == "received" and not has_interface:
            model_errors.append(f"{player}: missing interface")

    checks.append(
        _check(
            "collection_paths_match_expected_responses",
            not path_errors,
            category="structure",
            evidence="collection prompt/raw paths match expected response map"
            if not path_errors
            else "; ".join(path_errors[:8]),
        )
    )
    checks.append(
        _check(
            "received_responses_have_raw_files",
            not received_without_raw,
            category="collection",
            evidence="all received statuses have raw response files"
            if not received_without_raw
            else f"missing raw files for received players: {', '.join(received_without_raw)}",
        )
    )
    checks.append(
        _check(
            "raw_files_have_received_status",
            not raw_without_received,
            category="collection",
            evidence="all raw response files are marked received"
            if not raw_without_received
            else f"raw files without received status: {', '.join(raw_without_received)}",
        )
    )
    checks.append(
        _check(
            "received_responses_have_roster_metadata",
            not model_errors,
            category="participants",
            evidence="received responses have model identity and interface metadata"
            if not model_errors
            else "; ".join(model_errors[:8]),
        )
    )

    ready_for_raw_round = bool(expected_players) and sorted(ready_players) == expected_players
    checks.append(
        _check(
            "ready_for_raw_round",
            True,
            category="operator_flow",
            evidence="all expected responses are received with raw files and roster metadata"
            if ready_for_raw_round
            else f"ready={sorted(ready_players)} waiting={sorted(waiting_players)}",
        )
    )

    passed = all(check.passed for check in checks)
    return ExternalTrialStatusReport(
        pack_dir=str(root),
        passed=passed,
        ready_for_raw_round=ready_for_raw_round,
        response_count=len(response_entries),
        ready_players=sorted(ready_players),
        waiting_players=sorted(waiting_players),
        checks=checks,
    )


def render_external_trial_markdown(report: ExternalTrialReport) -> str:
    lines = [
        "# External Trial Preflight",
        "",
        f"Passed: `{str(report.passed).lower()}`",
        f"Match pack: `{report.pack_dir}`",
        f"Expected responses: `{report.response_count}`",
        "",
        "## Expected Players",
        "",
    ]
    if report.expected_players:
        lines.extend(f"- `{player}`" for player in report.expected_players)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| check | category | passed | evidence |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for check in report.checks:
        lines.append(f"| `{check.key}` | {check.category} | {str(check.passed).lower()} | {check.evidence} |")
    lines.append("")
    return "\n".join(lines)


def render_external_trial_status_markdown(report: ExternalTrialStatusReport) -> str:
    lines = [
        "# External Trial Collection Status",
        "",
        f"Passed: `{str(report.passed).lower()}`",
        f"Ready for raw-round: `{str(report.ready_for_raw_round).lower()}`",
        f"Match pack: `{report.pack_dir}`",
        f"Expected responses: `{report.response_count}`",
        "",
        "## Players",
        "",
        f"- Ready: `{', '.join(report.ready_players) or 'none'}`",
        f"- Waiting: `{', '.join(report.waiting_players) or 'none'}`",
        "",
        "## Checks",
        "",
        "| check | category | passed | evidence |",
        "| --- | --- | ---: | --- |",
    ]
    for check in report.checks:
        lines.append(f"| `{check.key}` | {check.category} | {str(check.passed).lower()} | {check.evidence} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preflight a generated external-AI trial kit before sending prompts.")
    parser.add_argument("match_pack", help="Generated match-pack directory")
    parser.add_argument(
        "--allow-existing-responses",
        action="store_true",
        help="Permit expected raw .txt response files to already exist.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    report = inspect_external_trial(
        args.match_pack,
        allow_existing_responses=args.allow_existing_responses,
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_external_trial_markdown(report))
    return 0 if report.passed else 1


def status_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect external-AI prompt sending and raw-response collection status.")
    parser.add_argument("match_pack", help="Generated match-pack directory")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Return non-zero unless every expected raw response is ready for raw-round.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    report = inspect_external_trial_status(args.match_pack)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_external_trial_status_markdown(report))
    if not report.passed:
        return 1
    if args.require_ready and not report.ready_for_raw_round:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
