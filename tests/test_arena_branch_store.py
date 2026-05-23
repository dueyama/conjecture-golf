import json

import pytest

from conjecture_golf.arena_branch_store import disqualified_players, main as branch_store_main, write_branch_store


def _quarantine(player: str, reason: str = "invalid_move") -> dict:
    return {
        "type": "quarantine",
        "player": player,
        "reason": reason,
        "verdict": {
            "ok": False,
            "kind": "invalid",
            "player": player,
            "message": "bad command",
            "score_delta": 0,
            "details": {},
        },
        "command": {"type": "invalid", "player": player},
    }


def test_branch_store_writes_canonical_and_quarantine_snapshots(tmp_path):
    canonical = [{"type": "score", "player": "careful"}]
    quarantine = [_quarantine("noise"), _quarantine("noise"), _quarantine("noise")]

    manifest = write_branch_store(
        canonical_records=canonical,
        quarantine_records=quarantine,
        decisions=[{"accepted": True}, {"accepted": False}],
        out_dir=tmp_path,
    )

    assert manifest["branches"]["arena/season-0"]["records"] == 1
    assert manifest["branches"]["quarantine/season-0"]["records"] == 3
    assert manifest["disqualified_players"] == [
        {"player": "noise", "invalid_strikes": 3, "threshold": 3}
    ]
    assert (tmp_path / "arena" / "season-0" / "transcript.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert (tmp_path / "quarantine" / "season-0" / "quarantine.jsonl").read_text(encoding="utf-8").count("\n") == 3
    disqualified = json.loads(
        (tmp_path / "quarantine" / "season-0" / "disqualified_players.json").read_text(encoding="utf-8")
    )
    assert disqualified[0]["player"] == "noise"


def test_branch_store_cli_reads_issue_handler_artifact_names(tmp_path, capsys):
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "arena-transcript.jsonl").write_text(
        json.dumps({"type": "score", "player": "careful"}) + "\n",
        encoding="utf-8",
    )
    (artifact / "quarantine-transcript.jsonl").write_text(
        "\n".join(json.dumps(_quarantine("noise")) for _ in range(3)) + "\n",
        encoding="utf-8",
    )
    (artifact / "arena-routing.json").write_text(
        json.dumps({"decisions": [{"accepted": True}, {"accepted": False}]}),
        encoding="utf-8",
    )
    out = tmp_path / "store"

    assert branch_store_main(["--artifact-root", str(artifact), "--out", str(out)]) == 0
    captured = capsys.readouterr()

    assert '"canonical_branch": "arena/season-0"' in captured.out
    assert (out / "branch-store-manifest.json").exists()
    assert (out / "routing-decisions.json").exists()


def test_disqualified_players_counts_only_invalid_verdicts():
    records = [
        _quarantine("noise"),
        {"type": "quarantine", "player": "noise", "verdict": {"kind": "counterexample"}},
        _quarantine("noise"),
        _quarantine("noise"),
    ]

    assert disqualified_players(records) == [{"player": "noise", "invalid_strikes": 3, "threshold": 3}]


def test_branch_store_rejects_unsafe_branch_names(tmp_path):
    with pytest.raises(ValueError):
        write_branch_store(
            canonical_records=[],
            quarantine_records=[],
            decisions=[],
            out_dir=tmp_path,
            canonical_branch="../arena",
        )
