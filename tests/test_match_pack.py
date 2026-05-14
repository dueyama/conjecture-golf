import json

from conjecture_golf.match_pack import build_match_pack


TRUE_FLOWER = {
    "type": "conjecture",
    "player": "blue",
    "name": "flower_growth",
    "if": [
        {"target_is": "."},
        {"exists": {"symbol": "W", "relation": "diagonal"}},
        {"exists": {"symbol": "F", "relation": "orthogonal"}},
        {"not_exists": {"symbol": "S", "relation": "king"}},
    ],
    "then": {"target_becomes": "F"},
}


def test_match_pack_contains_reports_and_templates(tmp_path):
    transcript = tmp_path / "match.jsonl"
    transcript.write_text(json.dumps(TRUE_FLOWER) + "\n", encoding="utf-8")
    out = tmp_path / "pack"

    build_match_pack(transcript, out)

    assert (out / "AI_PLAYER_GUIDE.md").exists()
    assert (out / "observer_report.md").read_text(encoding="utf-8").count("Newspaper") == 1
    assert (out / "frontier.md").exists()
    assert (out / "templates" / "conjecture.json").exists()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert "frontier.json" in manifest["files"]
