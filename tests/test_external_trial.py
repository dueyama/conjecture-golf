import json

from conjecture_golf.external_trial import (
    inspect_external_trial,
    inspect_external_trial_status,
    main as external_trial_main,
    status_main as external_trial_status_main,
)
from conjecture_golf.match_pack import build_match_pack
from conjecture_golf.season0 import main as season0_main


def _build_pack(tmp_path):
    out = tmp_path / "pack"
    build_match_pack(
        "examples/transcripts/basic.jsonl",
        out,
        season_path="seasons/season_0.json",
        participants=["model-a=frontier", "model-b=refuter"],
    )
    return out


def test_external_trial_preflight_passes_for_fresh_match_pack(tmp_path, capsys):
    pack = _build_pack(tmp_path)

    report = inspect_external_trial(pack)
    status = inspect_external_trial_status(pack)
    exit_code = season0_main(["trial-preflight", str(pack), "--json"])
    captured = capsys.readouterr()
    cli_report = json.loads(captured.out)

    assert report.passed
    assert status.passed
    assert not status.ready_for_raw_round
    assert status.waiting_players == ["model-a", "model-b"]
    assert report.response_count == 2
    assert report.expected_players == ["model-a", "model-b"]
    assert exit_code == 0
    assert cli_report["passed"] is True
    assert {check["key"] for check in cli_report["checks"]} >= {
        "expected_prompt_paths_exist",
        "raw_response_paths_are_safe_and_unique",
        "raw_responses_empty_before_send",
        "raw_round_command_is_reproducible",
    }


def test_external_trial_preflight_rejects_existing_raw_response_before_send(tmp_path):
    pack = _build_pack(tmp_path)
    (pack / "external_trial" / "raw_responses" / "model-a.txt").write_text(
        json.dumps({"type": "score", "player": "model-a"}),
        encoding="utf-8",
    )

    report = inspect_external_trial(pack)
    allowed = inspect_external_trial(pack, allow_existing_responses=True)
    checks = {check.key: check for check in report.checks}

    assert not report.passed
    assert not checks["raw_responses_empty_before_send"].passed
    assert "already exist" in checks["raw_responses_empty_before_send"].evidence
    assert allowed.passed


def test_external_trial_preflight_rejects_missing_prompt_file(tmp_path):
    pack = _build_pack(tmp_path)
    (pack / "copy_paste_prompts" / "model-a.md").unlink()

    report = inspect_external_trial(pack)
    checks = {check.key: check for check in report.checks}

    assert not report.passed
    assert not checks["expected_prompt_paths_exist"].passed
    assert "model-a" in checks["expected_prompt_paths_exist"].evidence


def test_external_trial_preflight_module_cli_reports_failure(tmp_path, capsys):
    pack = _build_pack(tmp_path)
    roster_path = pack / "external_trial" / "participant_roster.json"
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    roster["participants"][0]["external"] = False
    roster_path.write_text(json.dumps(roster), encoding="utf-8")

    exit_code = external_trial_main([str(pack), "--json"])
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert exit_code == 1
    assert report["passed"] is False
    failed = {check["key"] for check in report["checks"] if not check["passed"]}
    assert "roster_entries_match_expected_responses" in failed


def test_external_trial_status_requires_received_raw_files_and_roster_metadata(tmp_path, capsys):
    pack = _build_pack(tmp_path)
    status_path = pack / "external_trial" / "collection_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    for entry in status["participants"]:
        entry["status"] = "received"
        entry["prompt_sent_at"] = "2026-05-23T00:00:00Z"
        entry["response_received_at"] = "2026-05-23T00:01:00Z"
        raw_path = pack / entry["raw_response"]
        raw_path.write_text(json.dumps({"type": "score", "player": entry["player"]}), encoding="utf-8")
    status_path.write_text(json.dumps(status), encoding="utf-8")
    roster_path = pack / "external_trial" / "participant_roster.json"
    roster = json.loads(roster_path.read_text(encoding="utf-8"))
    for index, entry in enumerate(roster["participants"], start=1):
        entry["model_family"] = f"family-{index}"
        entry["model_name"] = f"model-{index}"
        entry["interface"] = "chat-ui"
    roster_path.write_text(json.dumps(roster), encoding="utf-8")

    report = inspect_external_trial_status(pack)
    exit_code = season0_main(["trial-status", str(pack), "--require-ready", "--json"])
    captured = capsys.readouterr()
    cli_report = json.loads(captured.out)

    assert report.passed
    assert report.ready_for_raw_round
    assert report.ready_players == ["model-a", "model-b"]
    assert exit_code == 0
    assert cli_report["ready_for_raw_round"] is True


def test_external_trial_status_module_cli_rejects_raw_without_received_status(tmp_path, capsys):
    pack = _build_pack(tmp_path)
    (pack / "external_trial" / "raw_responses" / "model-a.txt").write_text(
        json.dumps({"type": "score", "player": "model-a"}),
        encoding="utf-8",
    )

    exit_code = external_trial_status_main([str(pack), "--json"])
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert exit_code == 1
    assert report["passed"] is False
    failed = {check["key"] for check in report["checks"] if not check["passed"]}
    assert "raw_files_have_received_status" in failed
