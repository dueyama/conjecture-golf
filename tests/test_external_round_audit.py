import json

from conjecture_golf.external_round import run_external_round
from conjecture_golf.external_round_audit import audit_external_round, main as round_audit_main
from conjecture_golf.season0 import main as season0_main


def _score(player: str) -> dict[str, str]:
    return {"type": "score", "player": player}


def _roster(path):
    path.write_text(
        json.dumps(
            {
                "participants": [
                    {
                        "player": "model-a",
                        "external": True,
                        "kind": "llm_agent",
                        "model_family": "family-a",
                        "model_name": "model-a",
                        "interface": "chat-ui",
                        "strategy": "frontier",
                    },
                    {
                        "player": "model-b",
                        "external": True,
                        "kind": "llm_agent",
                        "model_family": "family-b",
                        "model_name": "model-b",
                        "interface": "chat-ui",
                        "strategy": "refuter",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_external_round_audit_passes_for_strict_raw_round_with_model_roster(tmp_path, capsys):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "model-a.txt").write_text(json.dumps(_score("model-a")), encoding="utf-8")
    (raw / "model-b.txt").write_text(json.dumps(_score("model-b")), encoding="utf-8")
    roster = _roster(tmp_path / "roster.json")
    out = tmp_path / "round"

    summary = run_external_round(
        "examples/transcripts/basic.jsonl",
        raw,
        out,
        participants=["model-a=frontier", "model-b=refuter"],
        participant_roster=roster,
        season_path="seasons/season_0.json",
    )
    report = audit_external_round(out, require_model_info=True, min_distinct_models=2)
    exit_code = season0_main(
        [
            "round-audit",
            str(out),
            "--require-model-info",
            "--min-distinct-models",
            "2",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    cli_report = json.loads(captured.out)

    assert summary["accepted"] == 2
    assert (out / "external_round_audit.json").exists()
    assert report.passed
    assert report.metrics["distinct_models"] == 2
    assert exit_code == 0
    assert cli_report["passed"] is True
    assert {check["key"] for check in cli_report["checks"]} >= {
        "strict_json_contract_passed_for_all_responses",
        "all_written_moves_entered_canonical_round",
        "external_roster_has_model_evidence",
        "next_match_pack_exists",
    }


def test_external_round_audit_rejects_contract_violation(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "model-a.txt").write_text(json.dumps(_score("model-a")), encoding="utf-8")
    (raw / "model-b.txt").write_text("Move:\n" + json.dumps(_score("model-b")), encoding="utf-8")
    roster = _roster(tmp_path / "roster.json")
    out = tmp_path / "round"

    run_external_round(
        "examples/transcripts/basic.jsonl",
        raw,
        out,
        participants=["model-a=frontier", "model-b=refuter"],
        participant_roster=roster,
        season_path="seasons/season_0.json",
    )
    report = audit_external_round(out)
    checks = {check.key: check for check in report.checks}

    assert not report.passed
    assert not checks["strict_json_contract_passed_for_all_responses"].passed
    assert not checks["all_written_moves_entered_canonical_round"].passed


def test_external_round_audit_module_cli_can_write_files(tmp_path, capsys):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "model-a.txt").write_text(json.dumps(_score("model-a")), encoding="utf-8")
    (raw / "model-b.txt").write_text(json.dumps(_score("model-b")), encoding="utf-8")
    roster = _roster(tmp_path / "roster.json")
    out = tmp_path / "round"
    run_external_round(
        "examples/transcripts/basic.jsonl",
        raw,
        out,
        participants=["model-a=frontier", "model-b=refuter"],
        participant_roster=roster,
        season_path="seasons/season_0.json",
    )

    exit_code = round_audit_main([str(out), "--require-model-info", "--min-distinct-models", "2", "--write", "--json"])
    captured = capsys.readouterr()
    report = json.loads(captured.out)

    assert exit_code == 0
    assert report["passed"] is True
    assert (out / "external_round_audit.json").exists()
    assert "External Round Audit" in (out / "external_round_audit.md").read_text(encoding="utf-8")
