from conjecture_golf.closed_test_audit import audit_records, main as audit_main, render_audit_markdown
from conjecture_golf.replay import iter_jsonl
from conjecture_golf.tournament import run_tournament


def test_closed_test_audit_passes_default_local_tournament():
    result = run_tournament(
        ["rule", "frontier", "characterizer", "greedy", "original_refuter", "minimalist", "random"],
        rounds=2,
        seed=0,
        season_scoring=True,
    )

    audit = audit_records(result.commands)
    data = audit.to_dict()

    assert audit.passed
    assert data["summary"]["game_moves"] >= 8
    assert len(data["summary"]["strategic_styles"]) >= 3
    assert data["summary"]["style_notes_by_player"]


def test_closed_test_audit_fails_small_sample_with_next_steps():
    audit = audit_records(iter_jsonl("examples/transcripts/basic.jsonl"))
    data = audit.to_dict()

    assert not audit.passed
    assert any(check["key"] == "enough_game_moves" and not check["passed"] for check in data["checks"])
    assert audit.next_steps


def test_closed_test_audit_markdown_and_cli(capsys):
    audit = audit_records(iter_jsonl("examples/transcripts/basic.jsonl"))
    markdown = render_audit_markdown(audit)

    assert "Closed Test Audit" in markdown
    assert "Strategic styles" in markdown

    exit_code = audit_main(["examples/transcripts/basic.jsonl", "--json"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert '"passed": false' in captured.out
