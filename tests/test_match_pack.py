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

    build_match_pack(transcript, out, season_path="seasons/season_0.json")

    assert (out / "AI_PLAYER_GUIDE.md").exists()
    quickstart = (out / "AI_ONE_PAGE_QUICKSTART.md").read_text(encoding="utf-8")
    assert "Output exactly one JSON object" in quickstart
    assert (out / "observer_report.md").read_text(encoding="utf-8").count("Newspaper") == 1
    assert (out / "frontier.md").exists()
    assert (out / "templates" / "conjecture.json").exists()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["season"]["season_id"] == "season_0"
    assert manifest["season_spec"] == "season_spec.json"
    assert (out / "season_spec.json").exists()
    assert "AI_ONE_PAGE_QUICKSTART.md" in manifest["files"]
    assert "frontier.json" in manifest["files"]
