import json

from conjecture_golf.chat_response import inspect_chat_response, main as chat_response_main


MOVE = {
    "type": "score",
    "player": "external-ai",
}


def test_chat_response_accepts_strict_json():
    report = inspect_chat_response(json.dumps(MOVE), expected_player="external-ai")

    assert report["contract_ok"] is True
    assert report["status"] == "strict_json"
    assert report["player_matches_expected"] is True
    assert report["violations"] == []


def test_chat_response_detects_markdown_and_prose_contract_violation():
    report = inspect_chat_response("Here is my move:\n```json\n" + json.dumps(MOVE) + "\n```")

    assert report["contract_ok"] is False
    assert report["status"] == "extracted_json_with_contract_violation"
    assert "markdown_fence" in report["violations"]
    assert "prose_outside_json" in report["violations"]
    assert report["extracted"]["player"] == "external-ai"


def test_chat_response_rejects_multiple_json_objects():
    report = inspect_chat_response(json.dumps(MOVE) + "\n" + json.dumps({"type": "score", "player": "other"}))

    assert report["contract_ok"] is False
    assert report["status"] == "multiple_json_objects"
    assert report["extracted"] is None


def test_chat_response_detects_player_mismatch():
    report = inspect_chat_response(json.dumps(MOVE), expected_player="wrong")

    assert report["contract_ok"] is False
    assert report["status"] == "player_mismatch"
    assert "player_mismatch" in report["violations"]


def test_chat_response_cli_writes_strict_move(tmp_path, capsys):
    response = tmp_path / "response.txt"
    response.write_text(json.dumps(MOVE), encoding="utf-8")
    out = tmp_path / "move.json"
    report_path = tmp_path / "report.json"

    exit_code = chat_response_main(
        [
            str(response),
            "--expected-player",
            "external-ai",
            "--out",
            str(out),
            "--report",
            str(report_path),
            "--json",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"contract_ok": true' in captured.out
    assert json.loads(out.read_text(encoding="utf-8"))["player"] == "external-ai"
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "strict_json"


def test_chat_response_cli_needs_allow_extraction_for_prose(tmp_path, capsys):
    response = tmp_path / "response.txt"
    response.write_text("Move:\n" + json.dumps(MOVE), encoding="utf-8")
    out = tmp_path / "move.json"

    exit_code = chat_response_main([str(response), "--out", str(out), "--json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert '"contract_ok": false' in captured.out
    assert not out.exists()

    exit_code = chat_response_main([str(response), "--out", str(out), "--allow-extraction", "--json"])

    assert exit_code == 0
    assert json.loads(out.read_text(encoding="utf-8"))["player"] == "external-ai"


def test_chat_response_cli_never_writes_player_mismatch(tmp_path, capsys):
    response = tmp_path / "response.txt"
    response.write_text(json.dumps(MOVE), encoding="utf-8")
    out = tmp_path / "move.json"

    exit_code = chat_response_main(
        [
            str(response),
            "--expected-player",
            "wrong-player",
            "--out",
            str(out),
            "--allow-extraction",
            "--json",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert '"status": "player_mismatch"' in captured.out
    assert not out.exists()
