import copy
import json
from pathlib import Path

from conjecture_golf.season_spec import load_season_spec, main as season_spec_main, validate_season_spec


def _base_spec():
    return json.loads(Path("seasons/season_0.json").read_text(encoding="utf-8"))


def _error_codes(spec):
    return {issue.code for issue in validate_season_spec(spec).errors}


def test_valid_bundled_specs_load():
    assert load_season_spec("seasons/season_0.json").season_id == "season_0"
    assert load_season_spec("seasons/season_1.json").season_id == "season_1"
    assert load_season_spec("seasons/candidates/season_1_moss_candidate.json").season_id == "season_1_moss_candidate"


def test_unknown_top_level_key_rejected():
    spec = _base_spec()
    spec["surprise"] = True

    assert "UNKNOWN_FIELD" in _error_codes(spec)


def test_unknown_rule_field_rejected():
    spec = _base_spec()
    spec["transition"]["rules"][0]["callback"] = "run_me"

    assert "UNKNOWN_FIELD" in _error_codes(spec)


def test_missing_required_field_rejected():
    spec = _base_spec()
    del spec["season_id"]

    assert "MISSING_REQUIRED_FIELD" in _error_codes(spec)


def test_invalid_board_size_rejected():
    spec = _base_spec()
    spec["board"]["width"] = 7

    assert "INVALID_BOARD_SIZE" in _error_codes(spec)


def test_symbol_errors_are_rejected():
    too_many = _base_spec()
    too_many["symbols"].extend(
        [
            {"id": "M", "name": "moss", "description": "moss"},
            {"id": "X", "name": "extra", "description": "extra"},
        ]
    )
    assert "TOO_MANY_SYMBOLS" in _error_codes(too_many)

    missing_empty = _base_spec()
    missing_empty["symbols"][0]["id"] = "E"
    assert "MISSING_EMPTY_SYMBOL" in _error_codes(missing_empty)

    duplicate = _base_spec()
    duplicate["symbols"][1]["id"] = "."
    assert "DUPLICATE_SYMBOL" in _error_codes(duplicate)


def test_relation_and_condition_errors_are_rejected():
    unknown_relation = _base_spec()
    unknown_relation["relations"] = ["orthogonal", "diagonal", "knight"]
    assert "INVALID_RELATION" in _error_codes(unknown_relation)

    unknown_kind = _base_spec()
    unknown_kind["transition"]["rules"][0]["when"][0] = {"or": []}
    assert "UNKNOWN_CONDITION_KIND" in _error_codes(unknown_kind)

    unknown_symbol = _base_spec()
    unknown_symbol["transition"]["rules"][0]["when"][0] = {"target_is": "M"}
    assert "UNKNOWN_CONDITION_SYMBOL" in _error_codes(unknown_symbol)

    unknown_becomes = _base_spec()
    unknown_becomes["transition"]["rules"][0]["becomes"] = "M"
    assert "UNKNOWN_BECOMES_SYMBOL" in _error_codes(unknown_becomes)


def test_duplicate_priority_rejected():
    spec = _base_spec()
    spec["transition"]["rules"][1]["priority"] = spec["transition"]["rules"][0]["priority"]

    assert "DUPLICATE_PRIORITY" in _error_codes(spec)


def test_trivial_count_policy_is_validated():
    spec = _base_spec()
    spec["conjecture_dsl"]["trivial_count_policy"] = "reject_count_at_least_zero"
    assert "INVALID_DSL" not in _error_codes(spec)

    bad = _base_spec()
    bad["conjecture_dsl"]["trivial_count_policy"] = "surprise"
    assert "INVALID_DSL" in _error_codes(bad)


def test_season_spec_cli_lint_render_smoke(capsys):
    assert season_spec_main(["lint", "seasons/season_0.json"]) == 0
    assert '"ok": true' in capsys.readouterr().out

    assert season_spec_main(["render", "seasons/season_0.json"]) == 0
    assert "Season: Season 0" in capsys.readouterr().out

    assert season_spec_main(["smoke", "seasons/season_0.json"]) == 0
    assert '"ok": true' in capsys.readouterr().out


def test_mutated_spec_helper_does_not_modify_base():
    spec = _base_spec()
    clone = copy.deepcopy(spec)
    clone["title"] = "Changed"

    assert spec["title"] == "Season 0"
