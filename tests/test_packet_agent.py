import json

from conjecture_golf.ai_state import build_ai_state_bundle, build_player_packet
from conjecture_golf.packet_agent import choose_packet_move, main as packet_agent_main
from conjecture_golf.replay import iter_jsonl
from conjecture_golf.submission_check import check_submission


def test_packet_agent_turns_player_packet_into_valid_move():
    records = list(iter_jsonl("examples/transcripts/basic.jsonl"))
    ai_state, move_candidates = build_ai_state_bundle(records)
    packet = build_player_packet(ai_state, move_candidates, player="model-a", strategy="frontier")

    move = choose_packet_move(packet)
    report = check_submission("examples/transcripts/basic.jsonl", move, expected_player="model-a")

    assert move["type"] == "conjecture"
    assert move["player"] == "model-a"
    assert report["accepted"] is True
    assert report["player_matches_expected"] is True
    assert report["verdict"]["kind"] == "conjecture"


def test_packet_agent_cli_writes_move(tmp_path, capsys):
    records = list(iter_jsonl("examples/transcripts/basic.jsonl"))
    ai_state, move_candidates = build_ai_state_bundle(records)
    packet = build_player_packet(ai_state, move_candidates, player="model-b", strategy="characterizer")
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    out = tmp_path / "move.json"

    exit_code = packet_agent_main([str(packet_path), "--out", str(out)])
    captured = capsys.readouterr()
    move = json.loads(out.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert json.loads(captured.out)["player"] == "model-b"
    assert move["player"] == "model-b"
    assert move["type"] == "conjecture"
