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

    build_match_pack(
        transcript,
        out,
        season_path="seasons/season_0.json",
        participants=["blue=lawwright", "external-ai=refuter"],
    )

    assert (out / "AI_PLAYER_GUIDE.md").exists()
    appeal = json.loads((out / "AI_APPEAL_AUDIT.json").read_text(encoding="utf-8"))
    assert "passed" in appeal
    assert "score" in appeal
    assert appeal["metrics"]["candidate_count"] > 0
    assert "competitive_titles_are_live" in {check["key"] for check in appeal["checks"]}
    assert "AI Appeal Audit" in (out / "AI_APPEAL_AUDIT.md").read_text(encoding="utf-8")
    quickstart = (out / "AI_ONE_PAGE_QUICKSTART.md").read_text(encoding="utf-8")
    assert "Output exactly one JSON object" in quickstart
    assert "player_packets/<your-player>.json" in quickstart
    assert "AI_STATE.json" in quickstart
    assert "MOVE_CANDIDATES.json" in quickstart
    assert "AI_APPEAL_AUDIT.json" in quickstart
    assert "agent_brief.md" in quickstart
    assert "participant_prompts/<your-player>.md" in quickstart
    assert "strategy_cards/<your-role>.md" in quickstart
    assert "standings.md" in quickstart
    assert "reference/REFERENCE_FILES.md" in quickstart
    assert "SELF_CHECK.md" in quickstart
    assert "exactly one JSON object" in (out / "PARTICIPANT_PROMPT.md").read_text(encoding="utf-8")
    assert "submission_check" in (out / "SELF_CHECK.md").read_text(encoding="utf-8")
    assert "chat_response" in (out / "CHAT_RESPONSE_INTAKE.md").read_text(encoding="utf-8")
    assert "intake transcript.jsonl" in (out / "OPERATOR_JUDGE_CARD.md").read_text(encoding="utf-8")
    assert "submission_check transcript.jsonl" in (out / "OPERATOR_JUDGE_CARD.md").read_text(encoding="utf-8")
    assert "chat_response raw_responses/<player>.txt" in (
        out / "OPERATOR_JUDGE_CARD.md"
    ).read_text(encoding="utf-8")
    assert "closed_match transcript.jsonl moves" in (out / "OPERATOR_JUDGE_CARD.md").read_text(encoding="utf-8")
    assert "minimalist" in (out / "dsl_summary.md").read_text(encoding="utf-8")
    assert (out / "participant_prompts" / "index.json").exists()
    prompt = (out / "participant_prompts" / "external-ai.md").read_text(encoding="utf-8")
    assert "You are `external-ai`" in prompt
    assert "Assigned strategy: `refuter`" in prompt
    assert "strategy_cards/refuter.md" in prompt
    assert '"player": "external-ai"' in prompt
    assert '--expected-player "external-ai"' in prompt
    assert (out / "COPY_PASTE_PROMPTS.md").exists()
    assert (out / "copy_paste_prompts" / "index.json").exists()
    paste_prompt = (out / "copy_paste_prompts" / "external-ai.md").read_text(encoding="utf-8")
    assert "Copy-Paste Prompt For External AI: external-ai" in paste_prompt
    assert 'Your JSON must include `"player": "external-ai"`' in paste_prompt
    assert "## Public Transcript" in paste_prompt
    assert (out / "player_packets" / "index.json").exists()
    packet = json.loads((out / "player_packets" / "external-ai.json").read_text(encoding="utf-8"))
    assert packet["schema"] == "conjecture_golf.player_packet.v1"
    assert packet["identity_lock"]["required_player"] == "external-ai"
    assert packet["strategy"] == "refuter"
    assert packet["candidate_lanes"]
    assert all(
        candidate["move_seed"]["player"] == "external-ai"
        for candidate in packet["candidate_lanes"]
        if "move_seed" in candidate
    )
    assert (out / "strategy_cards" / "index.json").exists()
    assert (out / "strategy_cards" / "refuter.md").exists()
    assert "original counterexample" in (out / "strategy_cards" / "refuter.md").read_text(encoding="utf-8")
    roster = json.loads((out / "participant_roster_template.json").read_text(encoding="utf-8"))
    assert roster["participants"][1]["player"] == "external-ai"
    assert roster["participants"][1]["external"] is True
    assert roster["participants"][1]["strategy"] == "refuter"
    assert "model_family" in roster["participants"][1]
    trial = json.loads((out / "external_trial" / "expected_responses.json").read_text(encoding="utf-8"))
    assert trial["responses"][1]["player"] == "external-ai"
    assert trial["responses"][1]["raw_response"] == "external_trial/raw_responses/external-ai.txt"
    collection = json.loads((out / "external_trial" / "collection_status.json").read_text(encoding="utf-8"))
    assert collection["schema"] == "conjecture_golf.external_trial_status.v1"
    assert collection["participants"][1]["status"] == "not_sent"
    trial_roster = json.loads((out / "external_trial" / "participant_roster.json").read_text(encoding="utf-8"))
    assert trial_roster["participants"][1]["prompt_sent"] == "copy_paste_prompts/external-ai.md"
    trial_readme = (out / "external_trial" / "README.md").read_text(encoding="utf-8")
    assert "season0 trial-preflight . --json" in trial_readme
    assert "season0 trial-status . --require-ready --json" in trial_readme
    assert "season0 raw-round transcript.jsonl external_trial/raw_responses" in trial_readme
    assert "season0 round-audit external_trial/round --require-model-info --json" in trial_readme
    assert "--participant-roster external_trial/participant_roster.json" in trial_readme
    assert "--final-external-evidence" in trial_readme
    assert (out / "external_trial" / "raw_responses" / "README.md").exists()
    assert (out / "external_trial" / "prompt_map" / "external-ai.md").exists()
    assert (out / "reference" / "REFERENCE_FILES.md").exists()
    assert (out / "reference" / "conjecture_golf" / "world.py").exists()
    assert (out / "reference" / "conjecture_golf" / "dsl.py").exists()
    assert "valid move is still exactly" in (
        out / "reference" / "REFERENCE_FILES.md"
    ).read_text(encoding="utf-8")
    assert (out / "observer_report.md").read_text(encoding="utf-8").count("Newspaper") == 1
    assert (out / "frontier.md").exists()
    ai_state = json.loads((out / "AI_STATE.json").read_text(encoding="utf-8"))
    assert ai_state["schema"] == "conjecture_golf.ai_state.v1"
    assert ai_state["audience"] == "machine_player"
    assert ai_state["frontier_tensor"]
    assert ai_state["participants"][1]["player"] == "external-ai"
    move_candidates = json.loads((out / "MOVE_CANDIDATES.json").read_text(encoding="utf-8"))
    assert move_candidates["schema"] == "conjecture_golf.move_candidates.v1"
    assert move_candidates["candidate_count"] > 0
    assert any(candidate["kind"] == "conjecture_seed" for candidate in move_candidates["candidates"])
    assert "Agent Turn Brief" in (out / "agent_brief.md").read_text(encoding="utf-8")
    assert (out / "standings.md").exists()
    assert (out / "player_briefs" / "index.json").exists()
    player_brief = (out / "player_briefs" / "blue.md").read_text(encoding="utf-8")
    assert "Your Title Opportunities" in player_brief
    assert "Recent Feedback" in player_brief
    assert (out / "templates" / "hello.json").exists()
    assert (out / "templates" / "conjecture.json").exists()
    contract = json.loads((out / "submission_contract.json").read_text(encoding="utf-8"))
    assert contract["format"] == "exactly_one_json_object"
    assert "unknown_fields" in contract["forbidden"]
    assert any("closed_match" in command for command in contract["validation_commands"])
    assert any("submission_check" in command for command in contract["validation_commands"])
    assert any("chat_response" in command for command in contract["validation_commands"])
    assert any("packet_agent" in command for command in contract["validation_commands"])
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["season"]["season_id"] == "season_0"
    assert manifest["season_spec"] == "season_spec.json"
    assert (out / "season_spec.json").exists()
    assert "AI_ONE_PAGE_QUICKSTART.md" in manifest["files"]
    assert "PARTICIPANT_PROMPT.md" in manifest["files"]
    assert "SELF_CHECK.md" in manifest["files"]
    assert "CHAT_RESPONSE_INTAKE.md" in manifest["files"]
    assert manifest["participant_prompts"]["external-ai"] == "participant_prompts/external-ai.md"
    assert manifest["copy_paste_prompts"]["external-ai"] == "copy_paste_prompts/external-ai.md"
    assert manifest["player_packets"]["external-ai"] == "player_packets/external-ai.json"
    assert manifest["participant_strategies"]["external-ai"] == "refuter"
    assert manifest["participant_roster_template"] == "participant_roster_template.json"
    assert manifest["external_trial"]["participant_roster"] == "external_trial/participant_roster.json"
    assert manifest["external_trial"]["raw_response_dir"] == "external_trial/raw_responses"
    assert manifest["external_trial"]["collection_status"] == "external_trial/collection_status.json"
    assert manifest["ai_appeal_audit"]["passed"] == appeal["passed"]
    assert manifest["ai_appeal_audit"]["json"] == "AI_APPEAL_AUDIT.json"
    assert manifest["strategy_cards"]["refuter"] == "strategy_cards/refuter.md"
    assert "AI_APPEAL_AUDIT.json" in manifest["files"]
    assert "AI_APPEAL_AUDIT.md" in manifest["files"]
    assert "participant_prompts/index.json" in manifest["files"]
    assert "participant_prompts/external-ai.md" in manifest["files"]
    assert "COPY_PASTE_PROMPTS.md" in manifest["files"]
    assert "copy_paste_prompts/index.json" in manifest["files"]
    assert "copy_paste_prompts/external-ai.md" in manifest["files"]
    assert "player_packets/index.json" in manifest["files"]
    assert "player_packets/external-ai.json" in manifest["files"]
    assert "participant_roster_template.json" in manifest["files"]
    assert "external_trial/README.md" in manifest["files"]
    assert "external_trial/collection_status.json" in manifest["files"]
    assert "external_trial/participant_roster.json" in manifest["files"]
    assert "external_trial/expected_responses.json" in manifest["files"]
    assert "external_trial/raw_responses/README.md" in manifest["files"]
    assert "strategy_cards/index.json" in manifest["files"]
    assert "strategy_cards/refuter.md" in manifest["files"]
    assert "reference/REFERENCE_FILES.md" in manifest["files"]
    assert "reference/conjecture_golf/world.py" in manifest["files"]
    assert "submission_contract.json" in manifest["files"]
    assert "frontier.json" in manifest["files"]
    assert "AI_STATE.json" in manifest["files"]
    assert "MOVE_CANDIDATES.json" in manifest["files"]
    assert "agent_brief.json" in manifest["files"]
    assert "player_briefs/blue.md" in manifest["files"]
    assert "standings.json" in manifest["files"]
