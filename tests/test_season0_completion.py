import importlib.util
import json
import re
from pathlib import Path

from conjecture_golf.replay import iter_jsonl
from conjecture_golf.season_eval import evaluate_records, main as season_eval_main


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


def test_operator_runbook_references_real_conjecture_golf_modules():
    text = Path("SEASON0_OPERATOR_RUNBOOK.md").read_text(encoding="utf-8")
    modules = sorted(set(re.findall(r"python -m (conjecture_golf\.[A-Za-z0-9_]+)", text)))

    assert "conjecture_golf.season_eval" in modules
    for module in modules:
        assert importlib.util.find_spec(module), module
