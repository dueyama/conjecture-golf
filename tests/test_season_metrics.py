import json
from pathlib import Path

from conjecture_golf.season_metrics import compute_season_metrics, lint_metrics
from conjecture_golf.season_spec import compile_season_spec, load_season_spec, main as season_spec_main


def _base_spec():
    return json.loads(Path("seasons/season_0.json").read_text(encoding="utf-8"))


def test_metrics_are_deterministic_for_season0():
    spec = load_season_spec("seasons/season_0.json")

    first = compute_season_metrics(spec)
    second = compute_season_metrics(spec)

    assert first.to_dict() == second.to_dict()
    assert first.local_neighborhood_count == 4**9
    assert first.transition_counts_by_before_after[".->F"] == 4225


def test_metrics_flag_all_stay_trivial_specs():
    spec_data = _base_spec()
    spec_data["transition"]["rules"] = [
        {
            "id": "impossible_rule",
            "priority": 1,
            "when": [
                {"target_is": "."},
                {"count_at_least": {"symbol": ".", "relation": "orthogonal", "n": 5}},
            ],
            "becomes": "F",
        }
    ]
    spec = compile_season_spec(spec_data)
    metrics = compute_season_metrics(spec)
    warning_codes = {warning.code for warning in lint_metrics(metrics)}

    assert metrics.change_ratio == 0
    assert "TRIVIAL_ALL_STAY" in warning_codes
    assert "RULE_NEVER_HITS" in warning_codes


def test_metrics_cli_json_outputs_machine_readable_payload(capsys):
    assert season_spec_main(["metrics", "seasons/season_0.json", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["season_id"] == "season_0"
    assert payload["schema_valid"] is True
