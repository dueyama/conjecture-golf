import json

from conjecture_golf.arena_issue import command_from_issue_comment, load_issue_comments, main as arena_issue_main, route_issue_comments


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


def _comment(comment_id: int, body: str, login: str = "player") -> dict:
    return {
        "id": comment_id,
        "created_at": f"2026-05-14T00:{comment_id:02d}:00Z",
        "body": body,
        "user": {"login": login},
    }


def _cg(payload: dict) -> str:
    return "/cg " + json.dumps(payload, separators=(",", ":"))


def test_command_from_issue_comment_turns_bad_cg_into_invalid_command():
    command = command_from_issue_comment(_comment(1, "/cg {not json}", login="noise"))

    assert command is not None
    assert command["type"] == "invalid"
    assert command["player"] == "noise"
    assert command["_meta"]["source"] == "github_issue"


def test_route_issue_comments_builds_canonical_and_quarantine_streams():
    comments = [
        _comment(1, _cg(TRUE_FLOWER), login="careful"),
        _comment(2, _cg({"type": "score", "player": "noise", "bonus": 999}), login="noise"),
    ]

    routing = route_issue_comments(comments)

    assert len(routing.canonical_records) == 1
    assert routing.canonical_records[0]["player"] == "careful"
    assert len(routing.quarantine_records) == 1
    assert routing.quarantine_records[0]["player"] == "noise"
    assert routing.decisions[0].branch == "arena/season-0"
    assert routing.decisions[1].branch == "quarantine/season-0"


def test_route_issue_comments_disqualifies_after_three_invalid_strikes():
    comments = [
        _comment(1, "/cg {not json}", login="noise"),
        _comment(2, "/cg {still not json}", login="noise"),
        _comment(3, _cg({"type": "score", "player": "noise", "bonus": 999}), login="noise"),
        _comment(4, _cg({**TRUE_FLOWER, "player": "noise"}), login="noise"),
    ]

    routing = route_issue_comments(comments)

    assert routing.current_decision is not None
    assert routing.current_decision.reason == "player_disqualified"
    assert routing.current_decision.canonical_command is None
    assert len(routing.canonical_records) == 0
    assert len(routing.quarantine_records) == 4


def test_load_issue_comments_accepts_jsonl(tmp_path):
    comments_path = tmp_path / "comments.jsonl"
    comments_path.write_text(
        json.dumps(_comment(1, "discussion")) + "\n" + json.dumps(_comment(2, _cg(TRUE_FLOWER))) + "\n",
        encoding="utf-8",
    )

    comments = load_issue_comments(comments_path)

    assert [comment["id"] for comment in comments] == [1, 2]


def test_arena_issue_cli_writes_replayable_streams(tmp_path, capsys):
    comments_path = tmp_path / "comments.json"
    canonical_path = tmp_path / "canonical.jsonl"
    quarantine_path = tmp_path / "quarantine.jsonl"
    decision_path = tmp_path / "decision.json"
    comments_path.write_text(
        json.dumps(
            [
                _comment(1, "discussion"),
                _comment(2, _cg(TRUE_FLOWER), login="careful"),
                _comment(3, _cg({"type": "score", "player": "noise", "bonus": 999}), login="noise"),
            ]
        ),
        encoding="utf-8",
    )

    exit_code = arena_issue_main(
        [
            str(comments_path),
            "--canonical",
            str(canonical_path),
            "--quarantine",
            str(quarantine_path),
            "--decision",
            str(decision_path),
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"canonical_records": 1' in captured.out
    assert canonical_path.read_text(encoding="utf-8").count("\n") == 1
    assert quarantine_path.read_text(encoding="utf-8").count("\n") == 1
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["decisions"][0]["branch"] == "arena/season-0"
    assert decision["decisions"][1]["branch"] == "quarantine/season-0"
