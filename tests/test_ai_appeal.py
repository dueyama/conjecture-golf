import json

from conjecture_golf.ai_appeal import assess_match_pack_ai_appeal, main as ai_appeal_main
from conjecture_golf.match_pack import build_match_pack
from conjecture_golf.season0 import main as season0_main


def _build_pack(tmp_path):
    out = tmp_path / "pack"
    build_match_pack(
        "examples/transcripts/basic.jsonl",
        out,
        season_path="seasons/season_0.json",
        participants=[
            "model-a=frontier",
            "model-b=refuter",
            "model-c=characterizer",
        ],
    )
    return out


def test_ai_appeal_passes_for_multi_role_match_pack(tmp_path, capsys):
    pack = _build_pack(tmp_path)

    report = assess_match_pack_ai_appeal(pack, validate_packets=True)
    exit_code = season0_main(["ai-appeal", str(pack), "--validate-packets", "--json"])
    captured = capsys.readouterr()
    cli_report = json.loads(captured.out)

    assert report.passed
    assert report.metrics["participants"] == 3
    assert report.metrics["packet_moves_accepted"] == 3
    assert report.metrics["moves_remaining"] > 0
    assert exit_code == 0
    assert cli_report["passed"] is True
    assert {check["key"] for check in cli_report["checks"]} >= {
        "season_has_continuation_pressure",
        "competitive_titles_are_live",
        "candidate_lanes_are_diverse",
        "packet_moves_are_locally_checkable",
        "external_trial_preflight_passes",
    }


def test_ai_appeal_rejects_single_participant_pack(tmp_path):
    out = tmp_path / "pack"
    build_match_pack(
        "examples/transcripts/basic.jsonl",
        out,
        season_path="seasons/season_0.json",
        participants=["solo=frontier"],
    )

    report = assess_match_pack_ai_appeal(out)
    checks = {check.key: check for check in report.checks}

    assert not report.passed
    assert not checks["participant_roles_support_various_ai_players"].passed
    assert checks["external_trial_preflight_passes"].passed


def test_ai_appeal_cli_reports_broken_external_trial(tmp_path, capsys):
    pack = _build_pack(tmp_path)
    (pack / "external_trial" / "raw_responses" / "model-a.txt").write_text(
        json.dumps({"type": "score", "player": "model-a"}),
        encoding="utf-8",
    )

    exit_code = ai_appeal_main([str(pack), "--json"])
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert exit_code == 1
    assert report["passed"] is False
    failed = {check["key"] for check in report["checks"] if not check["passed"]}
    assert "external_trial_preflight_passes" in failed
