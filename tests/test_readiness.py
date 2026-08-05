from conjecture_golf.readiness import main as readiness_main, render_readiness_markdown, run_readiness


def test_readiness_audit_passes_without_slow_playtest():
    report = run_readiness(include_playtest=False)
    checks = {check.key: check for check in report.checks}

    assert report.passed
    assert checks["transcript_replays_locally"].passed
    assert checks["issue_arena_quarantines_and_disqualifies"].passed
    assert checks["agent_brief_guides_next_move"].passed
    assert "participant prompt" in checks["match_pack_has_ai_surfaces"].evidence
    assert "copy-paste prompts" in checks["match_pack_has_ai_surfaces"].evidence
    assert "chat-response intake" in checks["match_pack_has_ai_surfaces"].evidence
    assert "external trial kit" in checks["match_pack_has_ai_surfaces"].evidence
    assert "AI appeal audit" in checks["match_pack_has_ai_surfaces"].evidence
    assert "machine AI state" in checks["match_pack_has_ai_surfaces"].evidence
    assert "move candidates" in checks["match_pack_has_ai_surfaces"].evidence
    assert "per-player machine packets" in checks["match_pack_has_ai_surfaces"].evidence
    assert "submission self-check" in checks["match_pack_has_ai_surfaces"].evidence
    assert "strategy cards" in checks["match_pack_has_ai_surfaces"].evidence
    assert checks["closed_match_batches_submissions"].passed
    assert checks["player_packet_generates_accepted_move"].passed
    assert checks["external_round_audit_proves_strict_raw_round"].passed
    assert checks["branch_store_snapshots_are_branch_ready"].passed
    assert checks["github_arena_packet_guides_next_ai_turn"].passed
    assert checks["workflow_is_closed_with_minimal_permissions"].passed
    assert "no active route" in checks["workflow_is_closed_with_minimal_permissions"].evidence
    assert "Issue comments" in report.remaining_human_steps[1]


def test_readiness_audit_includes_closed_test_gate_with_playtest():
    report = run_readiness(include_playtest=True)
    checks = {check.key: check for check in report.checks}

    assert report.passed
    assert checks["closed_test_audit_passes_on_local_rehearsal"].passed
    assert checks["packet_stale_pressure_visible"].passed


def test_readiness_markdown_lists_remaining_human_steps():
    report = run_readiness(include_playtest=False)
    markdown = render_readiness_markdown(report)

    assert "Conjecture Golf Readiness Audit" in markdown
    assert "remaining" in markdown.lower()
    assert "GitHub" in markdown


def test_readiness_cli_can_print_json(capsys):
    exit_code = readiness_main(["--skip-playtest", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert '"passed": true' in captured.out
    assert "multi_agent_playtest_passes" not in captured.out
