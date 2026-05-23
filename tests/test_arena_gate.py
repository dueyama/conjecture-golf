import json

from conjecture_golf.arena_gate import gate_move, main as gate_main


TRUE_FLOWER = {
    "type": "conjecture",
    "player": "careful",
    "name": "flower_growth",
    "if": [
        {"target_is": "."},
        {"exists": {"symbol": "W", "relation": "diagonal"}},
        {"exists": {"symbol": "F", "relation": "orthogonal"}},
        {"not_exists": {"symbol": "S", "relation": "king"}},
    ],
    "then": {"target_becomes": "F"},
}


FALSE_BUT_VALID = {
    "type": "conjecture",
    "player": "bold",
    "name": "too_broad",
    "if": [
        {"target_is": "."},
        {"exists": {"symbol": "W", "relation": "diagonal"}},
        {"exists": {"symbol": "F", "relation": "orthogonal"}},
    ],
    "then": {"target_becomes": "F"},
}


def _quarantine(player: str, strikes_after: int) -> dict:
    return {
        "type": "quarantine",
        "player": player,
        "reason": "invalid_move",
        "strikes_after": strikes_after,
        "verdict": {"kind": "invalid", "player": player},
        "command": {"type": "score", "player": player, "bonus": 999},
    }


def test_gate_accepts_valid_true_conjecture_to_canonical_branch():
    decision = gate_move([], [], TRUE_FLOWER)

    assert decision.accepted
    assert decision.branch == "arena/season-0"
    assert decision.canonical_command == TRUE_FLOWER
    assert decision.quarantine_record is None


def test_gate_accepts_false_but_well_formed_conjecture_to_canonical_branch():
    decision = gate_move([], [], FALSE_BUT_VALID)

    assert decision.accepted
    assert decision.verdict["kind"] == "conjecture"
    assert decision.verdict["ok"] is False


def test_gate_quarantines_schema_invalid_noise():
    decision = gate_move([], [], {"type": "score", "player": "noise", "bonus": 999})

    assert not decision.accepted
    assert decision.branch == "quarantine/season-0"
    assert decision.reason == "invalid_move"
    assert decision.strikes_after == 1
    assert decision.quarantine_record["player"] == "noise"


def test_gate_disqualifies_after_invalid_strikes():
    prior_quarantine = [_quarantine("noise", 1), _quarantine("noise", 2), _quarantine("noise", 3)]

    decision = gate_move([], prior_quarantine, {**TRUE_FLOWER, "player": "noise"})

    assert not decision.accepted
    assert decision.reason == "player_disqualified"
    assert decision.canonical_command is None
    assert decision.strikes_before == 3


def test_gate_cli_appends_to_routed_files(tmp_path, capsys):
    canonical = tmp_path / "canonical.jsonl"
    quarantine = tmp_path / "quarantine.jsonl"
    move = tmp_path / "move.json"
    move.write_text(json.dumps(TRUE_FLOWER), encoding="utf-8")

    exit_code = gate_main([str(canonical), str(move), "--quarantine", str(quarantine), "--append"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert canonical.exists()
    assert not quarantine.exists()
    assert '"accepted": true' in captured.out
