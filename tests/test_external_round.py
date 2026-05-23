import json
from pathlib import Path

from conjecture_golf.external_round import main as external_round_main, run_external_round
from conjecture_golf.season0 import main as season0_main


def _score(player: str) -> dict[str, str]:
    return {"type": "score", "player": player}


class _FakeAudit:
    passed = False

    def to_dict(self):
        return {
            "passed": self.passed,
            "checks": [],
            "summary": {
                "players": [],
                "game_moves": 0,
                "strategic_styles": [],
                "score_spread": 0,
                "moves_remaining": 24,
            },
            "next_steps": [],
        }


def _patch_artifact_writers(monkeypatch):
    def fake_write_closed_match_outputs(result, out_dir, **_kwargs):
        out = Path(out_dir)
        canonical = out / "canonical.jsonl"
        quarantine = out / "quarantine.jsonl"
        canonical.write_text(
            "".join(json.dumps(record, sort_keys=True) + "\n" for record in result.canonical_records),
            encoding="utf-8",
        )
        quarantine.write_text("", encoding="utf-8")
        return {"canonical": str(canonical), "quarantine": str(quarantine)}

    def fake_audit_records(_records, **_kwargs):
        return _FakeAudit()

    def fake_build_match_pack(_transcript, out_dir, **kwargs):
        out = Path(out_dir)
        prompt_dir = out / "participant_prompts"
        prompt_dir.mkdir(parents=True)
        for spec in kwargs.get("participants") or []:
            player = spec.rsplit("=", 1)[0]
            (prompt_dir / f"{player}.md").write_text(f"# {player}\n", encoding="utf-8")
        (out / "manifest.json").write_text("{}", encoding="utf-8")
        return {"out_dir": str(out), "manifest": str(out / "manifest.json"), "transcript": str(_transcript)}

    monkeypatch.setattr("conjecture_golf.external_round.write_closed_match_outputs", fake_write_closed_match_outputs)
    monkeypatch.setattr("conjecture_golf.external_round.audit_records", fake_audit_records)
    monkeypatch.setattr("conjecture_golf.external_round.build_match_pack", fake_build_match_pack)


def test_external_round_preserves_raw_reports_and_skips_contract_violation(tmp_path, monkeypatch):
    _patch_artifact_writers(monkeypatch)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "model-a.txt").write_text(json.dumps(_score("model-a")), encoding="utf-8")
    (raw / "model-b.txt").write_text("Move:\n" + json.dumps(_score("model-b")), encoding="utf-8")
    out = tmp_path / "round"

    summary = run_external_round(
        "examples/transcripts/basic.jsonl",
        raw,
        out,
        participants=["model-a=frontier", "model-b=refuter"],
    )

    assert summary["raw_responses"] == 2
    assert summary["moves_written"] == 1
    assert summary["accepted"] == 1
    assert summary["rejected"] == 0
    assert (out / "raw_responses" / "model-a.txt").exists()
    assert (out / "response_reports" / "model-a.report.json").exists()
    assert (out / "response_reports" / "model-b.report.json").exists()
    assert (out / "moves" / "model-a.json").exists()
    assert not (out / "moves" / "model-b.json").exists()
    assert (out / "external_round_summary.md").exists()
    assert (out / "next_match_pack" / "participant_prompts" / "model-b.md").exists()
    assert (out / "participant_roster_template.json").exists()
    assert summary["participant_roster_template"] == str(out / "participant_roster_template.json")
    assert summary["response_report_dir"] == str(out / "response_reports")
    assert summary["external_round_audit"] == str(out / "external_round_audit.json")
    assert (out / "external_round_audit.json").exists()
    assert "--participant-roster" in summary["evidence_command"]
    assert "--response-report-dir" in summary["evidence_command"]

    model_b_report = json.loads((out / "response_reports" / "model-b.report.json").read_text(encoding="utf-8"))
    assert model_b_report["status"] == "extracted_json_with_contract_violation"
    roster = json.loads((out / "participant_roster_template.json").read_text(encoding="utf-8"))
    assert roster["schema"] == "conjecture_golf.participant_roster.v1"
    assert roster["participants"][0]["player"] == "model-a"
    assert roster["participants"][0]["strategy"] == "frontier"
    assert roster["participants"][0]["response_report"].endswith("model-a.report.json")
    summary_md = (out / "external_round_summary.md").read_text(encoding="utf-8")
    assert "Evidence Handoff" in summary_md
    assert "model_family" in summary_md


def test_external_round_cli_can_salvage_single_json_with_allow_extraction(tmp_path, capsys, monkeypatch):
    _patch_artifact_writers(monkeypatch)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "model-a.txt").write_text(json.dumps(_score("model-a")), encoding="utf-8")
    (raw / "model-b.txt").write_text("Move:\n" + json.dumps(_score("model-b")), encoding="utf-8")
    out = tmp_path / "round"

    exit_code = external_round_main(
        [
            "examples/transcripts/basic.jsonl",
            str(raw),
            "--out",
            str(out),
            "--allow-extraction",
            "--participant",
            "model-a=frontier",
            "--participant",
            "model-b=refuter",
        ]
    )
    captured = capsys.readouterr()
    summary = json.loads((out / "external_round_summary.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert '"moves_written": 2' in captured.out
    assert summary["moves_written"] == 2
    assert summary["accepted"] == 2
    assert (out / "moves" / "model-b.json").exists()
    assert str(out / "participant_roster_template.json") in summary["evidence_command"]
    assert "--round-audit" in summary["evidence_command"]
    assert "--final-external-evidence" in summary["evidence_command"]


def test_external_round_preserves_filled_participant_roster_metadata(tmp_path, monkeypatch):
    _patch_artifact_writers(monkeypatch)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "model-a.txt").write_text(json.dumps(_score("model-a")), encoding="utf-8")
    roster = tmp_path / "roster.json"
    roster.write_text(
        json.dumps(
            {
                "participants": [
                    {
                        "player": "model-a",
                        "external": True,
                        "kind": "llm_agent",
                        "model_family": "family-a",
                        "model_name": "model-a-large",
                        "interface": "chat-ui",
                        "strategy": "frontier",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "round"

    summary = run_external_round(
        "examples/transcripts/basic.jsonl",
        raw,
        out,
        participants=["model-a=refuter"],
        participant_roster=roster,
    )
    generated = json.loads((out / "participant_roster_template.json").read_text(encoding="utf-8"))
    entry = generated["participants"][0]

    assert summary["participant_roster_source"] == str(roster)
    assert entry["player"] == "model-a"
    assert entry["model_family"] == "family-a"
    assert entry["model_name"] == "model-a-large"
    assert entry["interface"] == "chat-ui"
    assert entry["strategy"] == "refuter"
    assert entry["raw_response"].endswith("raw_responses/model-a.txt")
    assert entry["response_report"].endswith("response_reports/model-a.report.json")


def test_season0_raw_round_returns_nonzero_for_strict_failed_intake(tmp_path, monkeypatch):
    _patch_artifact_writers(monkeypatch)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "model-a.txt").write_text("Move:\n" + json.dumps(_score("model-a")), encoding="utf-8")
    out = tmp_path / "round"

    exit_code = season0_main(
        [
            "raw-round",
            "examples/transcripts/basic.jsonl",
            str(raw),
            "--out",
            str(out),
            "--participant",
            "model-a=frontier",
            "--strict-exit",
        ]
    )
    summary = json.loads((out / "external_round_summary.json").read_text(encoding="utf-8"))

    assert exit_code == 1
    assert summary["moves_written"] == 0
    assert summary["response_intake"][0]["wrote_move"] is False
    assert (out / "participant_roster_template.json").exists()
