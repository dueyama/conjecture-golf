import json

from conjecture_golf.ai_state import build_ai_state_bundle, build_player_packet, main as ai_state_main
from conjecture_golf.replay import iter_jsonl


def test_ai_state_exposes_machine_frontier_and_candidate_lanes():
    records = list(iter_jsonl("examples/transcripts/basic.jsonl"))

    ai_state, move_candidates = build_ai_state_bundle(records)

    assert ai_state["schema"] == "conjecture_golf.ai_state.v1"
    assert ai_state["audience"] == "machine_player"
    assert ai_state["transcript_records"] == 4
    assert ai_state["protocol"]["output_contract"] == "exactly_one_json_object_no_prose"
    assert ai_state["player_vectors"][0]["rank"] == 1
    assert ai_state["frontier_tensor"]
    assert any(row["open"] > 0 for row in ai_state["frontier_tensor"])
    assert ai_state["conjecture_index"]
    assert move_candidates["schema"] == "conjecture_golf.move_candidates.v1"
    assert move_candidates["transcript_digest"] == ai_state["transcript_digest"]
    assert any(candidate["kind"] == "conjecture_seed" for candidate in move_candidates["candidates"])
    assert any("unknown fields" in item for item in move_candidates["hard_constraints"])


def test_player_packet_locks_identity_and_specializes_move_seeds():
    records = list(iter_jsonl("examples/transcripts/basic.jsonl"))
    ai_state, move_candidates = build_ai_state_bundle(records)

    packet = build_player_packet(ai_state, move_candidates, player="model-a", strategy="frontier")

    assert packet["schema"] == "conjecture_golf.player_packet.v1"
    assert packet["player"] == "model-a"
    assert packet["strategy"] == "frontier"
    assert packet["identity_lock"]["move_json_must_contain"] == {"player": "model-a"}
    assert "stale_traps" in packet
    seeded = [candidate for candidate in packet["candidate_lanes"] if "move_seed" in candidate]
    assert seeded
    assert all(candidate["move_seed"]["player"] == "model-a" for candidate in seeded)
    assert any("model-a" in candidate["move_seed"].get("name", "") for candidate in seeded)


def test_ai_state_cli_can_print_candidate_json(capsys):
    exit_code = ai_state_main(["examples/transcripts/basic.jsonl", "--candidates"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["schema"] == "conjecture_golf.move_candidates.v1"
    assert payload["candidate_count"] > 0
