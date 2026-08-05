import hashlib
import json
from pathlib import Path

from conjecture_golf.replay import iter_jsonl


ARCHIVE = Path("seasons/archive/season_2")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_season2_archive_preserves_final_public_snapshot():
    transcript_path = ARCHIVE / "transcript.jsonl"
    packet_path = ARCHIVE / "AI_ARENA_PACKET.final.json"
    branch_state_path = ARCHIVE / "branch-state.json"

    records = list(iter_jsonl(transcript_path))
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    branch_state = json.loads(branch_state_path.read_text(encoding="utf-8"))

    assert len(records) == 12
    assert branch_state == {
        "branch": "arena/season-2",
        "description": "Accepted Conjecture Golf commands only. Replay this transcript locally.",
        "kind": "canonical",
        "quarantine_branch": "quarantine/season-2",
        "records": 12,
    }
    assert packet["branches"]["canonical"]["records"] == 12
    assert packet["branches"]["quarantine"]["records"] == 0
    assert packet["ruleset"] == {
        "commit": "5201be97474954b456a70f79e44d0bcd5e9ebe30",
        "policy": "Season judgments are valid for this rules ref and commit.",
        "ref": "season-2-rules",
        "season_id": "season_2",
    }
    assert packet["state"]["transcript_digest"] == _canonical_digest(records)
    assert packet["state"]["season"]["complete"] is False
    assert packet["state"]["season"]["moves_played"] == 12
    assert packet["state"]["season"]["moves_remaining"] == 36


def test_season2_archive_integrity_and_final_titles():
    packet = json.loads((ARCHIVE / "AI_ARENA_PACKET.final.json").read_text(encoding="utf-8"))
    title_races = {race["key"]: race for race in packet["state"]["title_races"]}

    assert _sha256(ARCHIVE / "transcript.jsonl") == (
        "bcddf6877c95598ca5f6918e9be37d47a39a7cfdb97476931427d5d751ea39b5"
    )
    assert _sha256(ARCHIVE / "AI_ARENA_PACKET.final.json") == (
        "06cf74228cf89aa82d323634870f0782b0718f9cf6c4be3683773b509ec67931"
    )
    assert _sha256(ARCHIVE / "branch-state.json") == (
        "2cd2fc74e444b3d3446a1f08b90f4916592e5d23698be3183323b803d50d45ec"
    )
    assert title_races["championship"]["leader"] == "codex-gpt-5"
    assert title_races["championship"]["value"] == 26
    assert title_races["lawwright"]["leader"] == "gpt-5.5-pro"
    assert title_races["refuter"]["leader"] is None


def test_project_docs_mark_season2_as_the_end():
    readme = Path("README.md").read_text(encoding="utf-8")
    summary = Path("seasons/season_2_summary.md").read_text(encoding="utf-8")

    assert "Project Status: Complete" in readme
    assert "There is no" in readme
    assert "active public arena and no Season 3" in readme
    assert "It is not Conjecture Golf Season 3" in summary
    assert "6af148149dddc028a5b8439ffcc7b330ba00f679" in summary
