"""Readiness audit for Conjecture Golf Season 0."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ai_appeal import assess_match_pack_ai_appeal
from .agent_brief import build_agent_brief
from .arena_branch_store import write_branch_store
from .arena_issue import route_issue_comments
from .arena_packet import build_arena_turn_packet
from .closed_match import run_closed_match, write_closed_match_outputs
from .external_round import run_external_round
from .external_round_audit import audit_external_round
from .external_trial import inspect_external_trial, inspect_external_trial_status
from .issue_protocol import parse_issue_comment
from .match_pack import build_match_pack
from .packet_agent import choose_packet_move, load_packet, write_move
from .packet_playtest import run_packet_stale_drill
from .playtest import run_playtest
from .replay import iter_jsonl, replay_records
from .season_catalog import load_optional_compiled_season
from .season_eval import evaluate_state
from .season_standings import build_season_standings_from_state
from .submission_check import check_submission
from .world import ValidationError


@dataclass(frozen=True)
class ReadinessCheck:
    key: str
    passed: bool
    category: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "passed": self.passed,
            "category": self.category,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ReadinessReport:
    passed: bool
    checks: list[ReadinessCheck]
    remaining_human_steps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "remaining_human_steps": self.remaining_human_steps,
        }


def _check(key: str, condition: bool, *, category: str, evidence: str) -> ReadinessCheck:
    return ReadinessCheck(key=key, passed=bool(condition), category=category, evidence=evidence)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _workflow_text() -> str:
    path = _repo_root() / ".github" / "workflows" / "issue-comment.yml"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _file_text(path: str) -> str:
    full_path = _repo_root() / path
    return full_path.read_text(encoding="utf-8") if full_path.exists() else ""


def _source_contains_any(needles: set[str]) -> bool:
    for path in (_repo_root() / "conjecture_golf").glob("*.py"):
        if path.name == "readiness.py":
            continue
        text = path.read_text(encoding="utf-8")
        if any(needle in text for needle in needles):
            return True
    return False


def _schema_rejects_unknown_fields() -> bool:
    try:
        parse_issue_comment('/cg {"type":"score","player":"p","bonus":999}')
    except ValidationError:
        return True
    return False


def _issue_arena_routes_bad_input() -> bool:
    routing = route_issue_comments(
        [
            {"id": 1, "body": "/cg {not json}", "user": {"login": "noise"}},
            {"id": 2, "body": "/cg {still not json}", "user": {"login": "noise"}},
            {
                "id": 3,
                "body": '/cg {"type":"score","player":"noise","bonus":999}',
                "user": {"login": "noise"},
            },
            {
                "id": 4,
                "body": '/cg {"type":"score","player":"noise"}',
                "user": {"login": "noise"},
            },
        ]
    )
    decision = routing.current_decision
    return bool(
        decision
        and decision.reason == "player_disqualified"
        and len(routing.canonical_records) == 0
        and len(routing.quarantine_records) == 4
    )


def _branch_store_snapshots_work() -> bool:
    routing = route_issue_comments(
        [
            {"id": 1, "body": '/cg {"type":"score","player":"careful"}', "user": {"login": "careful"}},
            {"id": 2, "body": "/cg {not json}", "user": {"login": "noise"}},
            {"id": 3, "body": "/cg {still not json}", "user": {"login": "noise"}},
            {
                "id": 4,
                "body": '/cg {"type":"score","player":"noise","bonus":999}',
                "user": {"login": "noise"},
            },
        ]
    )
    with tempfile.TemporaryDirectory() as tmp:
        manifest = write_branch_store(
            canonical_records=routing.canonical_records,
            quarantine_records=routing.quarantine_records,
            decisions=[decision.to_dict() for decision in routing.decisions],
            out_dir=tmp,
        )
        root = Path(tmp)
        return (
            manifest["disqualified_players"]
            and (root / "arena" / "season-0" / "transcript.jsonl").exists()
            and (root / "quarantine" / "season-0" / "disqualified_players.json").exists()
        )


def _github_arena_packet_guides_next_ai_turn() -> bool:
    routing = route_issue_comments(
        [
            {
                "id": 1,
                "body": '/cg {"type":"score","player":"careful"}',
                "user": {"login": "careful"},
            }
        ]
    )
    if routing.current_decision is None:
        return False
    packet = build_arena_turn_packet(
        canonical_records=routing.canonical_records,
        quarantine_records=routing.quarantine_records,
        decision=routing.current_decision,
        canonical_branch="arena/season-0",
        quarantine_branch="quarantine/season-0",
        invalid_strikes_to_disqualify=3,
    )
    return bool(
        packet["schema"] == "conjecture_golf.github_arena_turn.v1"
        and packet["audience"] == "github_ai_agent"
        and packet["protocol"]["move_surface"] == "GitHub Issue comment"
        and packet["state"]["transcript_digest"]
        and packet["state"]["candidate_lanes"]
    )


def _match_pack_has_ai_surfaces(transcript_path: str | Path) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "pack"
        build_match_pack(
            transcript_path,
            out,
            season_path="seasons/season_0.json",
            participants=[
                "readiness-ai=frontier",
                "readiness-refuter=refuter",
                "readiness-characterizer=characterizer",
            ],
        )
        expected = {
            "AI_ONE_PAGE_QUICKSTART.md",
            "AI_APPEAL_AUDIT.json",
            "AI_APPEAL_AUDIT.md",
            "PARTICIPANT_PROMPT.md",
            "OPERATOR_JUDGE_CARD.md",
            "SELF_CHECK.md",
            "CHAT_RESPONSE_INTAKE.md",
            "COPY_PASTE_PROMPTS.md",
            "AI_STATE.json",
            "MOVE_CANDIDATES.json",
            "agent_brief.md",
            "agent_brief.json",
            "participant_prompts/index.json",
            "player_packets/index.json",
            "copy_paste_prompts/index.json",
            "player_briefs/index.json",
            "strategy_cards/index.json",
            "submission_contract.json",
            "standings.md",
            "frontier.md",
            "observer_report.md",
            "reference/REFERENCE_FILES.md",
            "reference/conjecture_golf/world.py",
            "reference/conjecture_golf/dsl.py",
            "templates/conjecture.json",
            "templates/counterexample.json",
            "external_trial/README.md",
            "external_trial/collection_status.json",
            "external_trial/participant_roster.json",
            "external_trial/expected_responses.json",
        }
        if not all((out / item).exists() for item in expected):
            return False
        external_trial = inspect_external_trial(out)
        external_trial_status = inspect_external_trial_status(out)
        appeal = assess_match_pack_ai_appeal(out, validate_packets=True)
        index = json.loads((out / "player_briefs" / "index.json").read_text(encoding="utf-8"))
        if not index:
            return False
        first_brief = out / next(iter(index.values()))
        observer_report = (out / "observer_report.md").read_text(encoding="utf-8")
        return (
            "Recent Feedback" in first_brief.read_text(encoding="utf-8")
            and "Match story" in observer_report
            and "Style Notes" in observer_report
            and "submission_check" in (out / "SELF_CHECK.md").read_text(encoding="utf-8")
            and "chat_response" in (out / "CHAT_RESPONSE_INTAKE.md").read_text(encoding="utf-8")
            and "Copy-Paste Prompts" in (out / "COPY_PASTE_PROMPTS.md").read_text(encoding="utf-8")
            and "raw-round" in (out / "external_trial" / "README.md").read_text(encoding="utf-8")
            and external_trial.passed
            and external_trial_status.passed
            and appeal.passed
            and json.loads((out / "AI_STATE.json").read_text(encoding="utf-8"))["audience"] == "machine_player"
            and json.loads((out / "MOVE_CANDIDATES.json").read_text(encoding="utf-8"))["candidate_count"] > 0
            and json.loads((out / "player_packets" / "readiness-ai.json").read_text(encoding="utf-8"))[
                "identity_lock"
            ]["required_player"]
            == "readiness-ai"
        )


def _closed_match_batch_works(transcript_path: str | Path) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        moves = Path(tmp) / "moves"
        moves.mkdir()
        (moves / "01-score.json").write_text(
            json.dumps({"type": "score", "player": "closed-match-smoke"}),
            encoding="utf-8",
        )
        (moves / "02-bad.json").write_text("{not json}", encoding="utf-8")
        result = run_closed_match(transcript_path, moves)
        outputs = write_closed_match_outputs(result, Path(tmp) / "round")
        observer_report = Path(outputs["observer_report"]).read_text(encoding="utf-8")
        evaluation = json.loads(Path(outputs["season_eval_json"]).read_text(encoding="utf-8"))
        return (
            result.accepted_count == 1
            and result.rejected_count == 1
            and len(result.quarantine_records) == 1
            and "Match story" in observer_report
            and "style_notes_by_player" in evaluation
        )


def _packet_agent_generates_accepted_move(transcript_path: str | Path) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pack = root / "pack"
        moves = root / "moves"
        build_match_pack(
            transcript_path,
            pack,
            season_path="seasons/season_0.json",
            participants=["readiness-ai=frontier"],
        )
        packet = load_packet(pack / "player_packets" / "readiness-ai.json")
        move = choose_packet_move(packet)
        move_path = moves / "readiness-ai.json"
        write_move(move_path, move)
        report = check_submission(
            pack / "transcript.jsonl",
            move,
            expected_player="readiness-ai",
            season=load_optional_compiled_season("seasons/season_0.json"),
        )
        return (
            report["accepted"] is True
            and report["player_matches_expected"] is True
            and move_path.exists()
        )


def _external_round_audit_works(transcript_path: str | Path) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw = root / "raw"
        raw.mkdir()
        (raw / "readiness-a.txt").write_text(
            json.dumps({"type": "score", "player": "readiness-a"}),
            encoding="utf-8",
        )
        (raw / "readiness-b.txt").write_text(
            json.dumps({"type": "score", "player": "readiness-b"}),
            encoding="utf-8",
        )
        roster = root / "participant_roster.json"
        _write_roster = {
            "participants": [
                {
                    "player": "readiness-a",
                    "external": True,
                    "kind": "llm_agent",
                    "model_family": "readiness-family-a",
                    "model_name": "readiness-model-a",
                    "interface": "local fixture",
                    "strategy": "frontier",
                },
                {
                    "player": "readiness-b",
                    "external": True,
                    "kind": "llm_agent",
                    "model_family": "readiness-family-b",
                    "model_name": "readiness-model-b",
                    "interface": "local fixture",
                    "strategy": "refuter",
                },
            ]
        }
        roster.write_text(json.dumps(_write_roster), encoding="utf-8")
        out = root / "round"
        run_external_round(
            transcript_path,
            raw,
            out,
            participants=["readiness-a=frontier", "readiness-b=refuter"],
            participant_roster=roster,
            season_path="seasons/season_0.json",
        )
        report = audit_external_round(
            out,
            require_model_info=True,
            min_distinct_models=2,
        )
        return report.passed and (out / "external_round_audit.json").exists()


def _packet_stale_pressure_works(transcript_path: str | Path) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        summary = run_packet_stale_drill(
            out_dir=Path(tmp) / "stale-drill",
            source=transcript_path,
            season_path="seasons/season_0.json",
        )
        checks = {check["key"]: check for check in summary["closed_test_audit"]["checks"]}
        return bool(
            summary["stale_pressure_visible"]
            and summary["evaluation"]["stale_moves"] > 0
            and checks["has_stale_or_duplicate_pressure"]["passed"]
        )


def run_readiness(
    *,
    transcript_path: str | Path = "examples/transcripts/basic.jsonl",
    include_playtest: bool = True,
) -> ReadinessReport:
    records = list(iter_jsonl(transcript_path))
    state = replay_records(records, season_scoring=True)
    evaluation = evaluate_state(state)
    standings = build_season_standings_from_state(state)
    brief = build_agent_brief(standings)
    workflow = _workflow_text()
    readme = _file_text("README.md")
    security = _file_text("SECURITY.md")

    checks = [
        _check(
            "transcript_replays_locally",
            len(state.verdicts) == len(records) and bool(state.scores),
            category="self_judging",
            evidence=f"{len(state.verdicts)} public records replayed with deterministic scoring.",
        ),
        _check(
            "season_has_competitive_state",
            bool(standings.title_races) and bool(standings.next_objectives) and not standings.season_complete,
            category="gameplay",
            evidence=f"{len(standings.title_races)} title races, {len(standings.next_objectives)} next objectives.",
        ),
        _check(
            "agent_brief_guides_next_move",
            bool(brief["recommendations"]) and bool(brief["submission_contract"]),
            category="ai_participation",
            evidence="agent brief has recommendations and a JSON submission contract.",
        ),
        _check(
            "match_pack_has_ai_surfaces",
            _match_pack_has_ai_surfaces(transcript_path),
            category="ai_participation",
            evidence="match pack includes quickstart, participant prompt, copy-paste prompts, chat-response intake, external trial kit with preflight, AI appeal audit, machine AI state, move candidates, per-player machine packets, submission self-check, strategy cards, judge card, agent brief, player briefs with recent feedback, standings, frontier, observer report with match story/style notes, public source references, contract, and templates.",
        ),
        _check(
            "closed_match_batches_submissions",
            _closed_match_batch_works(transcript_path),
            category="ai_participation",
            evidence="closed_match batch accepts a valid move, quarantines malformed JSON, and writes evaluation/observer artifacts for the next round.",
        ),
        _check(
            "player_packet_generates_accepted_move",
            _packet_agent_generates_accepted_move(transcript_path),
            category="ai_participation",
            evidence="a per-player machine packet can produce one accepted JSON move through packet_agent and submission_check.",
        ),
        _check(
            "external_round_audit_proves_strict_raw_round",
            _external_round_audit_works(transcript_path),
            category="ai_participation",
            evidence="raw external-AI replies can be preserved, strictly inspected, accepted, rostered, and audited for continuation evidence.",
        ),
        _check(
            "schema_rejects_unknown_issue_fields",
            _schema_rejects_unknown_fields(),
            category="security",
            evidence="unknown /cg fields are rejected before replay.",
        ),
        _check(
            "issue_arena_quarantines_and_disqualifies",
            _issue_arena_routes_bad_input(),
            category="security",
            evidence="malformed/schema-invalid comments reconstruct to quarantine and strike-based disqualification.",
        ),
        _check(
            "branch_store_snapshots_are_branch_ready",
            _branch_store_snapshots_work(),
            category="security",
            evidence="arena routing can be written as canonical and quarantine branch snapshots with a disqualified-player ledger.",
        ),
        _check(
            "github_arena_packet_guides_next_ai_turn",
            _github_arena_packet_guides_next_ai_turn(),
            category="github_alpha",
            evidence="Issue verdict comments include a compact JSON AI Arena Packet with routing, branch, strike, title-race, and candidate-lane state.",
        ),
        _check(
            "workflow_uses_minimal_permissions_and_gate",
            "contents: read" in workflow
            and "issues: write" in workflow
            and "CG_ARENA_GATE" in workflow
            and "CG_RULES_REF: season-0-rules" in workflow
            and "ref: ${{ env.CG_RULES_REF }}" in workflow,
            category="github_alpha",
            evidence="issue-comment workflow uses read contents, write issues, arena gate mode, and the fixed season-0-rules checkout.",
        ),
        _check(
            "public_comments_are_reconstructable",
            "python -m conjecture_golf.arena_issue comments.json" in readme
            and "workflow secrets or private state" in security,
            category="reproducibility",
            evidence="docs explain public Issue comment export and local reconstruction.",
        ),
        _check(
            "no_eval_or_exec_in_engine",
            not _source_contains_any({"eval(", "exec("}),
            category="security",
            evidence="conjecture_golf Python sources contain no eval( or exec( calls.",
        ),
        _check(
            "no_external_ai_dependency",
            all(token not in _file_text("pyproject.toml") for token in ("openai", "anthropic", "google-generativeai")),
            category="security",
            evidence="project dependencies do not include external AI API clients.",
        ),
        _check(
            "sample_transcript_has_play_arc",
            evaluation.valid_conjectures > 0 and evaluation.valid_counterexamples > 0,
            category="gameplay",
            evidence=f"{evaluation.valid_conjectures} valid conjectures and {evaluation.valid_counterexamples} valid counterexamples in sample transcript.",
        ),
    ]

    if include_playtest:
        playtest_report, _ = run_playtest()
        checks.append(
            _check(
                "multi_agent_playtest_passes",
                playtest_report.passed,
                category="gameplay",
                evidence=f"{len(playtest_report.agents)} agents, {playtest_report.commands} commands, criteria={playtest_report.criteria}.",
            )
        )
        local_audit = playtest_report.closed_test_audit
        checks.append(
            _check(
                "closed_test_audit_passes_on_local_rehearsal",
                bool(local_audit["passed"]),
                category="gameplay",
                evidence=(
                    f"{len(local_audit['summary']['players'])} players, "
                    f"{local_audit['summary']['game_moves']} game moves, "
                    f"styles={local_audit['summary']['strategic_styles']}."
                ),
            )
        )
        checks.append(
            _check(
                "packet_stale_pressure_visible",
                _packet_stale_pressure_works(transcript_path),
                category="gameplay",
                evidence="packet stale drill keeps legal stale moves canonical while exposing stale/duplicate pressure.",
            )
        )

    passed = all(check.passed for check in checks)
    return ReadinessReport(
        passed=passed,
        checks=checks,
        remaining_human_steps=[
            "Do not publish to GitHub until the operator explicitly asks.",
            "If opening a public arena, decide whether public Issue comments alone are the source of truth or remote canonical/quarantine branches are the durable store.",
            "Keep chat-only external trial tooling optional; it is not required for the GitHub-native arena loop.",
        ],
    )


def render_readiness_markdown(report: ReadinessReport) -> str:
    lines = [
        "# Conjecture Golf Readiness Audit",
        "",
        f"Passed: `{str(report.passed).lower()}`",
        "",
        "| check | category | passed | evidence |",
        "| --- | --- | ---: | --- |",
    ]
    for check in report.checks:
        lines.append(f"| `{check.key}` | {check.category} | {str(check.passed).lower()} | {check.evidence} |")
    lines.extend(["", "## Remaining Human Steps", ""])
    for step in report.remaining_human_steps:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Conjecture Golf Season 0 readiness.")
    parser.add_argument("--transcript", default="examples/transcripts/basic.jsonl")
    parser.add_argument("--skip-playtest", action="store_true", help="Skip the slower deterministic multi-agent playtest.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    args = parser.parse_args(argv)

    report = run_readiness(transcript_path=args.transcript, include_playtest=not args.skip_playtest)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_readiness_markdown(report))
    return 0 if report.passed else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
