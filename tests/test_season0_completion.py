import importlib.util
import json
import re
from pathlib import Path

from conjecture_golf.replay import iter_jsonl
from conjecture_golf.season_engine import load_compiled_season
from conjecture_golf.season_eval import evaluate_records, main as season_eval_main
from conjecture_golf.season0 import main as season0_main


def test_season_manifest_exists_and_has_required_fields():
    manifest = json.loads(Path("season_manifest.json").read_text(encoding="utf-8"))

    for key in [
        "season_id",
        "world_version",
        "dsl_version",
        "scoring_version",
        "reveal_policy_default",
        "board_size",
        "symbols",
        "claim_kinds",
    ]:
        assert key in manifest
    assert manifest["season_id"] == "season_0"
    assert manifest["board_size"] == 5
    assert manifest["claim_kinds"] == ["sufficient", "necessary", "equivalence"]


def test_season_eval_runs_on_basic_transcript(capsys):
    exit_code = season_eval_main(["examples/transcripts/basic.jsonl"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Season Evaluation" in captured.out
    assert "total moves" in captured.out


def test_season_eval_detects_deterministic_styles():
    evaluation = evaluate_records(iter_jsonl("examples/transcripts/basic.jsonl"))
    data = evaluation.to_dict()

    assert data["total_moves"] == 4
    assert data["valid_conjectures"] >= 1
    assert data["has_two_distinct_strategic_styles"]
    assert "codex-blue" in data["style_notes_by_player"]
    assert any("frontier opener" in note for note in data["style_notes_by_player"]["codex-blue"])


def test_season_eval_accepts_season_spec():
    season = load_compiled_season("seasons/season_0.json")
    evaluation = evaluate_records(iter_jsonl("examples/transcripts/basic.jsonl"), season=season)

    assert evaluation.to_dict()["season_id"] == "season_0"
    assert evaluation.to_dict()["total_moves"] == 4


def test_season0_report_writes_standings(tmp_path):
    out = tmp_path / "reports"

    exit_code = season0_main(["report", "examples/transcripts/basic.jsonl", "--out", str(out)])

    assert exit_code == 0
    assert "Season Standings" in (out / "standings.md").read_text(encoding="utf-8")


def test_season0_round_judges_moves_and_generates_next_pack(tmp_path):
    moves = tmp_path / "moves"
    moves.mkdir()
    (moves / "external-ai.json").write_text(
        json.dumps({"type": "score", "player": "external-ai"}),
        encoding="utf-8",
    )
    out = tmp_path / "round"

    exit_code = season0_main(
        [
            "round",
            "examples/transcripts/basic.jsonl",
            str(moves),
            "--out",
            str(out),
            "--participant",
            "external-ai",
        ]
    )
    summary = json.loads((out / "round_summary.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert summary["accepted"] == 1
    assert summary["rejected"] == 0
    assert (out / "canonical.jsonl").exists()
    assert (out / "quarantine.jsonl").exists()
    assert (out / "closed_test_audit.json").exists()
    assert (out / "next_match_pack" / "manifest.json").exists()
    prompt = (out / "next_match_pack" / "participant_prompts" / "external-ai.md").read_text(encoding="utf-8")
    assert '"player": "external-ai"' in prompt


def test_season0_evidence_bundles_reproducible_audit(tmp_path):
    out = tmp_path / "evidence"

    exit_code = season0_main(
        [
            "evidence",
            "examples/transcripts/basic.jsonl",
            "--out",
            str(out),
            "--season",
            "seasons/season_0.json",
        ]
    )
    summary = json.loads((out / "evidence_summary.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert (out / "transcript.jsonl").exists()
    assert (out / "season_spec.json").exists()
    assert (out / "EVIDENCE.md").exists()
    assert (out / "closed_test_audit.json").exists()
    assert (out / "observer_report.md").exists()
    assert summary["season_spec"] == "season_spec.json"
    assert summary["participant_roster"] is None
    assert summary["participant_evidence"]["status"] == "not_checked"
    assert summary["final_external_evidence"]["status"] == "not_required"
    assert summary["closed_test_audit"]["passed"] is False
    assert any("closed_test_audit transcript.jsonl" in command for command in summary["verification_commands"])
    assert "Not Yet Proven" in (out / "EVIDENCE.md").read_text(encoding="utf-8")


def test_season0_evidence_records_external_participant_roster(tmp_path):
    roster = tmp_path / "roster.json"
    roster.write_text(
        json.dumps(
            {
                "participants": [
                    {"player": "codex-blue", "external": True, "kind": "llm_agent", "model": "model-a"},
                    {"player": "codex-red", "external": True, "kind": "llm_agent", "model": "model-b"},
                    {"player": "gpt-green", "external": True, "kind": "llm_agent", "model": "model-c"},
                    {"player": "observer", "external": True, "kind": "llm_agent", "model": "model-d"},
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "evidence"

    exit_code = season0_main(
        [
            "evidence",
            "examples/transcripts/basic.jsonl",
            "--out",
            str(out),
            "--participant-roster",
            str(roster),
            "--require-external-participants",
        ]
    )
    summary = json.loads((out / "evidence_summary.json").read_text(encoding="utf-8"))
    evidence_md = (out / "EVIDENCE.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert (out / "participant_roster.json").exists()
    assert (out / "participant_roster.md").exists()
    assert summary["participant_roster"] == "participant_roster.json"
    assert summary["participant_evidence"]["status"] == "passed"
    assert summary["participant_evidence"]["passed"] is True
    assert summary["participant_evidence"]["model_diversity_status"] == "passed"
    assert summary["participant_evidence"]["model_diversity_passed"] is True
    assert len(summary["participant_evidence"]["distinct_external_models"]) == 4
    assert summary["final_external_evidence"]["status"] == "not_required"
    assert "External participant evidence: `passed`" in evidence_md
    assert "Model diversity: `passed`" in evidence_md


def test_season0_evidence_can_require_model_diversity(tmp_path):
    roster = tmp_path / "roster.json"
    roster.write_text(
        json.dumps(
            {
                "participants": [
                    {"player": "codex-blue", "external": True, "kind": "llm_agent", "model": "model-a"},
                    {"player": "codex-red", "external": True, "kind": "llm_agent", "model": "model-b"},
                    {"player": "gpt-green", "external": True, "kind": "llm_agent", "model": "model-c"},
                    {"player": "observer", "external": True, "kind": "llm_agent", "model": "model-d"},
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "evidence"

    exit_code = season0_main(
        [
            "evidence",
            "examples/transcripts/basic.jsonl",
            "--out",
            str(out),
            "--participant-roster",
            str(roster),
            "--require-external-participants",
            "--require-model-diversity",
        ]
    )
    summary = json.loads((out / "evidence_summary.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert summary["participant_evidence"]["model_diversity_status"] == "passed"
    assert summary["participant_evidence"]["model_diversity_required"] is True


def test_season0_evidence_fails_when_required_model_diversity_is_missing(tmp_path):
    roster = tmp_path / "roster.json"
    roster.write_text(
        json.dumps(
            {
                "participants": [
                    {"player": "codex-blue", "external": True, "kind": "llm_agent", "model": "same-model"},
                    {"player": "codex-red", "external": True, "kind": "llm_agent", "model": "same-model"},
                    {"player": "gpt-green", "external": True, "kind": "llm_agent", "model": ""},
                    {"player": "observer", "external": True, "kind": "llm_agent"},
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "evidence"

    exit_code = season0_main(
        [
            "evidence",
            "examples/transcripts/basic.jsonl",
            "--out",
            str(out),
            "--participant-roster",
            str(roster),
            "--require-external-participants",
            "--require-model-diversity",
        ]
    )
    summary = json.loads((out / "evidence_summary.json").read_text(encoding="utf-8"))
    evidence_md = (out / "EVIDENCE.md").read_text(encoding="utf-8")

    assert exit_code == 1
    assert summary["participant_evidence"]["model_diversity_status"] == "failed"
    assert summary["participant_evidence"]["model_diversity_passed"] is False
    assert summary["participant_evidence"]["missing_model_info"] == ["gpt-green", "observer"]
    assert "Model Diversity Gap" in evidence_md


def test_season0_evidence_can_require_response_reports(tmp_path):
    players = ["codex-blue", "codex-red", "gpt-green", "observer"]
    roster = tmp_path / "roster.json"
    roster.write_text(
        json.dumps(
            {
                "participants": [
                    {"player": player, "external": True, "kind": "llm_agent", "model": f"model-{index}"}
                    for index, player in enumerate(players, start=1)
                ]
            }
        ),
        encoding="utf-8",
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    for player in players:
        (reports / f"{player}.report.json").write_text(
            json.dumps(
                {
                    "contract_ok": True,
                    "expected_player": player,
                    "extracted": {"type": "score", "player": player},
                    "json_objects_found": 1,
                    "player": player,
                    "player_matches_expected": True,
                    "status": "strict_json",
                    "violations": [],
                }
            ),
            encoding="utf-8",
        )
    out = tmp_path / "evidence"

    exit_code = season0_main(
        [
            "evidence",
            "examples/transcripts/basic.jsonl",
            "--out",
            str(out),
            "--participant-roster",
            str(roster),
            "--require-external-participants",
            "--response-report-dir",
            str(reports),
            "--require-response-reports",
        ]
    )
    summary = json.loads((out / "evidence_summary.json").read_text(encoding="utf-8"))
    evidence_md = (out / "EVIDENCE.md").read_text(encoding="utf-8")

    assert exit_code == 0
    assert summary["submission_provenance"]["status"] == "passed"
    assert summary["submission_provenance"]["passed"] is True
    assert sorted(summary["submission_provenance"]["machine_checked_players"]) == players
    assert summary["final_external_evidence"]["checks"]["submission_provenance"] is True
    assert summary["response_report_dir"] == "response_reports"
    assert (out / "response_reports" / "01-codex-blue.report.json").exists()
    assert "Submission provenance: `passed`" in evidence_md


def test_season0_evidence_fails_when_required_response_report_is_missing(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "codex-blue.report.json").write_text(
        json.dumps(
            {
                "contract_ok": True,
                "expected_player": "codex-blue",
                "extracted": {"type": "score", "player": "codex-blue"},
                "json_objects_found": 1,
                "player": "codex-blue",
                "player_matches_expected": True,
                "status": "strict_json",
                "violations": [],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "evidence"

    exit_code = season0_main(
        [
            "evidence",
            "examples/transcripts/basic.jsonl",
            "--out",
            str(out),
            "--response-report-dir",
            str(reports),
            "--require-response-reports",
        ]
    )
    summary = json.loads((out / "evidence_summary.json").read_text(encoding="utf-8"))
    evidence_md = (out / "EVIDENCE.md").read_text(encoding="utf-8")

    assert exit_code == 1
    assert summary["submission_provenance"]["status"] == "failed"
    assert "codex-red" in summary["submission_provenance"]["missing_reports"]
    assert "Submission Provenance Gap" in evidence_md


def test_season0_evidence_final_external_gate_requires_all_proof_conditions(tmp_path):
    players = ["codex-blue", "codex-red", "gpt-green", "observer"]
    roster = tmp_path / "roster.json"
    roster.write_text(
        json.dumps(
            {
                "participants": [
                    {"player": player, "external": True, "kind": "llm_agent", "model": f"model-{index}"}
                    for index, player in enumerate(players, start=1)
                ]
            }
        ),
        encoding="utf-8",
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    for player in players:
        (reports / f"{player}.report.json").write_text(
            json.dumps(
                {
                    "contract_ok": True,
                    "expected_player": player,
                    "extracted": {"type": "score", "player": player},
                    "json_objects_found": 1,
                    "player": player,
                    "player_matches_expected": True,
                    "status": "strict_json",
                    "violations": [],
                }
            ),
            encoding="utf-8",
        )
    round_audit = tmp_path / "round_audit.json"
    round_audit.write_text(
        json.dumps(
            {
                "passed": True,
                "metrics": {
                    "expected_players": players,
                    "raw_responses": len(players),
                    "moves_written": len(players),
                    "accepted": len(players),
                    "rejected": 0,
                    "next_pack_ai_appeal": {"passed": True, "score": "13/13"},
                },
                "checks": [],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "evidence"

    exit_code = season0_main(
        [
            "evidence",
            "examples/transcripts/basic.jsonl",
            "--out",
            str(out),
            "--participant-roster",
            str(roster),
            "--response-report-dir",
            str(reports),
            "--round-audit",
            str(round_audit),
            "--final-external-evidence",
        ]
    )
    summary = json.loads((out / "evidence_summary.json").read_text(encoding="utf-8"))
    evidence_md = (out / "EVIDENCE.md").read_text(encoding="utf-8")

    assert exit_code == 1
    assert summary["participant_evidence"]["required"] is True
    assert summary["participant_evidence"]["model_diversity_required"] is True
    assert summary["submission_provenance"]["required"] is True
    assert summary["round_audit_evidence"]["required"] is True
    assert summary["round_audit_evidence"]["continuation_appeal_required"] is True
    assert summary["round_audit_evidence"]["passed"] is True
    assert summary["final_external_evidence"]["required"] is True
    assert summary["final_external_evidence"]["status"] == "failed"
    assert summary["final_external_evidence"]["checks"] == {
        "closed_test_audit": False,
        "external_participants": True,
        "model_diversity": True,
        "submission_provenance": True,
        "round_audit": True,
    }
    assert "Final Evidence Gap" in evidence_md


def test_season0_evidence_final_external_gate_requires_round_audit(tmp_path):
    players = ["codex-blue", "codex-red", "gpt-green", "observer"]
    roster = tmp_path / "roster.json"
    roster.write_text(
        json.dumps(
            {
                "participants": [
                    {"player": player, "external": True, "kind": "llm_agent", "model": f"model-{index}"}
                    for index, player in enumerate(players, start=1)
                ]
            }
        ),
        encoding="utf-8",
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    for player in players:
        (reports / f"{player}.report.json").write_text(
            json.dumps(
                {
                    "contract_ok": True,
                    "expected_player": player,
                    "extracted": {"type": "score", "player": player},
                    "json_objects_found": 1,
                    "player": player,
                    "player_matches_expected": True,
                    "status": "strict_json",
                    "violations": [],
                }
            ),
            encoding="utf-8",
        )
    out = tmp_path / "evidence"

    exit_code = season0_main(
        [
            "evidence",
            "examples/transcripts/basic.jsonl",
            "--out",
            str(out),
            "--participant-roster",
            str(roster),
            "--response-report-dir",
            str(reports),
            "--final-external-evidence",
        ]
    )
    summary = json.loads((out / "evidence_summary.json").read_text(encoding="utf-8"))
    evidence_md = (out / "EVIDENCE.md").read_text(encoding="utf-8")

    assert exit_code == 1
    assert summary["round_audit_evidence"]["status"] == "failed"
    assert summary["round_audit_evidence"]["passed"] is False
    assert summary["final_external_evidence"]["checks"]["round_audit"] is False
    assert "Round Audit Gap" in evidence_md


def test_season0_evidence_final_external_gate_requires_round_audit_continuation(tmp_path):
    players = ["codex-blue", "codex-red", "gpt-green", "observer"]
    roster = tmp_path / "roster.json"
    roster.write_text(
        json.dumps(
            {
                "participants": [
                    {"player": player, "external": True, "kind": "llm_agent", "model": f"model-{index}"}
                    for index, player in enumerate(players, start=1)
                ]
            }
        ),
        encoding="utf-8",
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    for player in players:
        (reports / f"{player}.report.json").write_text(
            json.dumps(
                {
                    "contract_ok": True,
                    "expected_player": player,
                    "extracted": {"type": "score", "player": player},
                    "json_objects_found": 1,
                    "player": player,
                    "player_matches_expected": True,
                    "status": "strict_json",
                    "violations": [],
                }
            ),
            encoding="utf-8",
        )
    round_audit = tmp_path / "round_audit.json"
    round_audit.write_text(
        json.dumps(
            {
                "passed": True,
                "metrics": {
                    "expected_players": players,
                    "raw_responses": len(players),
                    "moves_written": len(players),
                    "accepted": len(players),
                    "rejected": 0,
                },
                "checks": [],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "evidence"

    exit_code = season0_main(
        [
            "evidence",
            "examples/transcripts/basic.jsonl",
            "--out",
            str(out),
            "--participant-roster",
            str(roster),
            "--response-report-dir",
            str(reports),
            "--round-audit",
            str(round_audit),
            "--final-external-evidence",
        ]
    )
    summary = json.loads((out / "evidence_summary.json").read_text(encoding="utf-8"))
    evidence_md = (out / "EVIDENCE.md").read_text(encoding="utf-8")

    assert exit_code == 1
    assert summary["round_audit_evidence"]["status"] == "failed"
    assert summary["round_audit_evidence"]["passed"] is False
    assert summary["round_audit_evidence"]["missing_continuation_appeal"]
    assert summary["final_external_evidence"]["checks"]["round_audit"] is False
    assert "next-pack AI appeal evidence" in evidence_md


def test_season0_experiment_runs_closed_match_rehearsal(tmp_path):
    out = tmp_path / "experiment"

    exit_code = season0_main(
        [
            "experiment",
            "--out",
            str(out),
            "--rounds",
            "2",
            "--agent",
            "greedy",
            "--agent",
            "minimalist",
            "--agent",
            "rule",
        ]
    )
    summary = json.loads((out / "experiment_summary.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert (out / "round-01" / "observer_report.md").exists()
    assert (out / "round-02" / "player_briefs" / "index.json").exists()
    assert (out / "final_transcript.jsonl").exists()
    assert (out / "next_match_pack" / "manifest.json").exists()
    assert (out / "next_match_pack" / "participant_prompts" / "greedy-agent.md").exists()
    assert (out / "closed_test_audit.json").exists()
    assert len(summary["rounds"]) == 2
    assert summary["evaluation"]["has_two_distinct_strategic_styles"]
    assert "closed_test_audit" in summary


def test_operator_runbook_references_real_conjecture_golf_modules():
    text = Path("SEASON0_OPERATOR_RUNBOOK.md").read_text(encoding="utf-8")
    modules = sorted(set(re.findall(r"python -m (conjecture_golf\.[A-Za-z0-9_]+)", text)))

    assert "conjecture_golf.season_eval" in modules
    for module in modules:
        assert importlib.util.find_spec(module), module
