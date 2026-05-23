import json

from conjecture_golf.arena_issue import route_issue_comments
from conjecture_golf.arena_packet import build_arena_turn_packet, render_arena_turn_packet_markdown


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


def _comment(comment_id: int, payload: dict, login: str = "player") -> dict:
    return {
        "id": comment_id,
        "created_at": f"2026-05-14T00:{comment_id:02d}:00Z",
        "body": "/cg " + json.dumps(payload, separators=(",", ":")),
        "user": {"login": login},
    }


def test_arena_turn_packet_is_machine_next_turn_state():
    routing = route_issue_comments([_comment(1, TRUE_FLOWER, login="careful")])
    assert routing.current_decision is not None

    packet = build_arena_turn_packet(
        canonical_records=routing.canonical_records,
        quarantine_records=routing.quarantine_records,
        decision=routing.current_decision,
        canonical_branch="arena/season-0",
        quarantine_branch="quarantine/season-0",
        invalid_strikes_to_disqualify=3,
    )
    markdown = render_arena_turn_packet_markdown(packet)

    assert packet["schema"] == "conjecture_golf.github_arena_turn.v1"
    assert packet["audience"] == "github_ai_agent"
    assert packet["protocol"]["move_surface"] == "GitHub Issue comment"
    assert packet["routing"]["accepted"] is True
    assert packet["branches"]["canonical"]["name"] == "arena/season-0"
    assert packet["branches"]["quarantine"]["name"] == "quarantine/season-0"
    assert packet["state"]["transcript_digest"]
    assert packet["state"]["candidate_lanes"]
    assert "unknown JSON fields are invalid" in packet["hard_constraints"]
    assert "AI Arena Packet" in markdown
    assert "conjecture_golf.github_arena_turn.v1" in markdown
