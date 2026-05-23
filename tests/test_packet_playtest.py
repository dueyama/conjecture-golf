import json

from conjecture_golf.packet_playtest import main as packet_playtest_main, run_packet_playtest, run_packet_stale_drill


def test_packet_playtest_runs_closed_match_from_player_packets(tmp_path):
    out = tmp_path / "packet-playtest"

    summary = run_packet_playtest(
        out_dir=out,
        source="examples/transcripts/basic.jsonl",
        participants=[
            "packet-frontier=frontier",
            "packet-characterizer=characterizer",
            "packet-lawwright=lawwright",
        ],
        rounds=1,
        season_path="seasons/season_0.json",
    )

    assert summary["rounds"][0]["accepted"] == 3
    assert summary["rounds"][0]["rejected"] == 0
    assert (out / "round-01" / "match_pack" / "player_packets" / "packet-frontier.json").exists()
    assert (out / "round-01" / "moves" / "packet-frontier.json").exists()
    assert (out / "final_transcript.jsonl").read_text(encoding="utf-8").count("\n") == 7
    assert (out / "next_match_pack" / "MOVE_CANDIDATES.json").exists()
    assert summary["closed_test_audit"]["summary"]["game_moves"] >= 5


def test_packet_playtest_cli_writes_summary(tmp_path, capsys):
    out = tmp_path / "packet-playtest"

    exit_code = packet_playtest_main(
        [
            "--out",
            str(out),
            "--source",
            "examples/transcripts/basic.jsonl",
            "--season",
            "seasons/season_0.json",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["rounds"][0]["accepted"] == 3
    assert (out / "packet_playtest_summary.json").exists()


def test_packet_stale_drill_makes_stale_pressure_visible(tmp_path):
    out = tmp_path / "packet-stale-drill"

    summary = run_packet_stale_drill(
        out_dir=out,
        source="examples/transcripts/basic.jsonl",
        season_path="seasons/season_0.json",
    )

    assert summary["stale_pressure_visible"] is True
    assert summary["phases"][0]["accepted"] == 1
    assert summary["phases"][1]["accepted"] == 1
    assert summary["evaluation"]["stale_moves"] > 0
    assert any(
        check["key"] == "has_stale_or_duplicate_pressure" and check["passed"]
        for check in summary["closed_test_audit"]["checks"]
    )
    assert (out / "packet_stale_drill_summary.json").exists()
