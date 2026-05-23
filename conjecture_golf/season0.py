"""Convenience wrapper for local Season 0 operations."""

from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .ai_appeal import assess_match_pack_ai_appeal, render_ai_appeal_markdown
from .arena_gate import iter_quarantine_jsonl
from .closed_test_audit import audit_records, render_audit_markdown
from .closed_match import run_closed_match, write_closed_match_outputs
from .external_round import run_external_round
from .external_round_audit import audit_external_round, render_external_round_audit_markdown, write_external_round_audit
from .external_trial import (
    inspect_external_trial,
    inspect_external_trial_status,
    render_external_trial_markdown,
    render_external_trial_status_markdown,
)
from .frontier import build_frontier_report_from_records, render_frontier_markdown
from .intake import append_move, load_move, prepare_move, validate_move
from .local_agents import available_agents, next_agent_command
from .match_pack import build_match_pack
from .observer_report import render_html_report, render_report
from .replay import iter_jsonl, replay_file, replay_records
from .score import leaderboard_rows, render_markdown
from .season_catalog import load_optional_compiled_season
from .season_eval import evaluate_records, render_evaluation_markdown
from .season_standings import build_season_standings, render_standings_markdown

DEFAULT_EXPERIMENT_AGENTS = [
    "rule",
    "frontier",
    "characterizer",
    "greedy",
    "original_refuter",
    "minimalist",
    "random",
]


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            f.write("\n")


def _cmd_init(args: argparse.Namespace) -> int:
    source = Path(args.source)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, out)
    print(f"Wrote Season 0 transcript: {out}")
    return 0


def _cmd_pack(args: argparse.Namespace) -> int:
    build_match_pack(
        args.transcript,
        args.out,
        min_player_interval_seconds=args.min_player_interval_seconds,
        reveal_policy=args.reveal_policy,
        season_path=args.season,
        participants=args.participants,
    )
    print(f"Wrote match pack to {args.out}")
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    season = load_optional_compiled_season(args.season)
    move = prepare_move(load_move(args.move), player=args.player)
    _state, verdict = validate_move(
        args.transcript,
        move,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season=season,
    )
    print(json.dumps(verdict.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    if verdict.kind == "invalid":
        return 1
    if args.append:
        append_move(args.transcript, move)
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    records = list(iter_jsonl(args.transcript))
    season = load_optional_compiled_season(args.season)

    state = replay_file(args.transcript, season_scoring=True, season=season)
    (out / "leaderboard.md").write_text(render_markdown(leaderboard_rows(state.scores)) + "\n", encoding="utf-8")

    frontier = build_frontier_report_from_records(records, season=season)
    (out / "frontier.md").write_text(render_frontier_markdown(frontier), encoding="utf-8")

    (out / "observer_report.md").write_text(
        render_report(records, season_scoring=True, reveal_policy=args.reveal_policy, season=season),
        encoding="utf-8",
    )
    (out / "observer_report.html").write_text(
        render_html_report(records, season_scoring=True, reveal_policy=args.reveal_policy, season=season),
        encoding="utf-8",
    )

    evaluation = evaluate_records(records, season=season)
    (out / "season_eval.md").write_text(render_evaluation_markdown(evaluation), encoding="utf-8")

    standings = build_season_standings(records, season=season)
    (out / "standings.md").write_text(render_standings_markdown(standings), encoding="utf-8")
    print(f"Wrote Season 0 reports to {out}")
    return 0


def _players_from_round(result: Any) -> list[str]:
    players: list[str] = []
    seen: set[str] = set()
    for decision in result.decisions:
        player = str(decision.player).strip()
        if player and player not in seen:
            players.append(player)
            seen.add(player)
    return players


def _cmd_round(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    season = load_optional_compiled_season(args.season)
    prior_quarantine_records = iter_quarantine_jsonl(args.prior_quarantine) if args.prior_quarantine else None

    result = run_closed_match(
        args.transcript,
        args.moves_dir,
        pattern=args.pattern,
        prior_quarantine_records=prior_quarantine_records,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=True,
        season=season,
        invalid_strikes_to_disqualify=args.invalid_strikes_to_disqualify,
    )
    outputs = write_closed_match_outputs(
        result,
        out,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=True,
        season=season,
        reveal_policy=args.reveal_policy,
    )
    audit = audit_records(result.canonical_records, season=season, move_cap=args.move_cap)
    (out / "closed_test_audit.md").write_text(render_audit_markdown(audit), encoding="utf-8")
    _write_json(out / "closed_test_audit.json", audit.to_dict())

    participants = args.participants or _players_from_round(result)
    next_pack = out / "next_match_pack"
    build_match_pack(
        outputs["canonical"],
        next_pack,
        min_player_interval_seconds=args.min_player_interval_seconds,
        reveal_policy=args.reveal_policy,
        season_path=args.season,
        participants=participants,
    )

    summary = {
        "accepted": result.accepted_count,
        "rejected": result.rejected_count,
        "participants": participants,
        "outputs": outputs,
        "closed_test_audit": audit.to_dict(),
        "next_match_pack": str(next_pack),
    }
    _write_json(out / "round_summary.json", summary)
    lines = [
        "# Season 0 Round Summary",
        "",
        f"Accepted moves: `{result.accepted_count}`",
        f"Rejected/quarantined moves: `{result.rejected_count}`",
        f"Next match pack: `{next_pack}`",
        "",
        "## Participants",
        "",
    ]
    if participants:
        lines.extend(f"- `{player}`" for player in participants)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Audit",
            "",
            f"Closed-test audit passed: `{str(audit.passed).lower()}`",
            "",
        ]
    )
    (out / "round_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _cmd_raw_round(args: argparse.Namespace) -> int:
    summary = run_external_round(
        args.transcript,
        args.raw_response_dir,
        args.out,
        pattern=args.pattern,
        participants=args.participants,
        participant_roster=args.participant_roster,
        allow_extraction=args.allow_extraction,
        prior_quarantine=args.prior_quarantine,
        min_player_interval_seconds=args.min_player_interval_seconds,
        invalid_strikes_to_disqualify=args.invalid_strikes_to_disqualify,
        move_cap=args.move_cap,
        reveal_policy=args.reveal_policy,
        season_path=args.season,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    failed_intake = any(not item["wrote_move"] for item in summary["response_intake"])
    if args.strict_exit and (failed_intake or summary["rejected"]):
        return 1
    return 0


def _cmd_round_audit(args: argparse.Namespace) -> int:
    report = audit_external_round(
        args.round_dir,
        min_external_participants=args.min_external_participants,
        min_distinct_models=args.min_distinct_models,
        require_model_info=args.require_model_info,
        require_next_pack_appeal=args.require_next_pack_appeal,
        validate_next_pack_packets=args.validate_next_pack_packets,
    )
    if args.write:
        write_external_round_audit(args.round_dir, report)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_external_round_audit_markdown(report))
    return 0 if report.passed else 1


def _cmd_trial_preflight(args: argparse.Namespace) -> int:
    report = inspect_external_trial(
        args.match_pack,
        allow_existing_responses=args.allow_existing_responses,
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_external_trial_markdown(report))
    return 0 if report.passed else 1


def _cmd_trial_status(args: argparse.Namespace) -> int:
    report = inspect_external_trial_status(args.match_pack)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_external_trial_status_markdown(report))
    if not report.passed:
        return 1
    if args.require_ready and not report.ready_for_raw_round:
        return 1
    return 0


def _cmd_ai_appeal(args: argparse.Namespace) -> int:
    report = assess_match_pack_ai_appeal(
        args.match_pack,
        validate_packets=args.validate_packets,
    )
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_ai_appeal_markdown(report))
    return 0 if report.passed else 1


def _evidence_verification_commands(season_spec_name: str | None) -> list[str]:
    season_flag = f" --season {season_spec_name}" if season_spec_name else ""
    return [
        f"python -m conjecture_golf.replay transcript.jsonl --season-scoring{season_flag}",
        f"python -m conjecture_golf.season_eval transcript.jsonl{season_flag}",
        f"python -m conjecture_golf.closed_test_audit transcript.jsonl{season_flag}",
    ]


def _load_participant_roster(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    participants = payload.get("participants") if isinstance(payload, dict) else payload
    if not isinstance(participants, list):
        raise ValueError("participant roster must be a list or an object with a participants list")
    roster: list[dict[str, Any]] = []
    for index, item in enumerate(participants, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"participant roster entry {index} must be an object")
        player = str(item.get("player", "")).strip()
        if not player:
            raise ValueError(f"participant roster entry {index} is missing player")
        roster.append(dict(item, player=player))
    return roster


def _players_in_records(records: list[dict[str, Any]]) -> set[str]:
    return {str(record.get("player", "")).strip() for record in records if str(record.get("player", "")).strip()}


def _participant_evidence(
    records: list[dict[str, Any]],
    roster: list[dict[str, Any]],
    *,
    min_external_participants: int,
    require_external_participants: bool,
    min_distinct_models: int,
    require_model_diversity: bool,
) -> dict[str, Any]:
    transcript_players = _players_in_records(records)
    external_entries = [
        entry
        for entry in roster
        if entry.get("external") is True and str(entry["player"]) in transcript_players
    ]
    external_players = sorted(str(entry["player"]) for entry in external_entries)
    model_identity_by_player = {
        str(entry["player"]): str(
            entry.get("model")
            or entry.get("model_name")
            or entry.get("model_family")
            or ""
        ).strip()
        for entry in external_entries
    }
    distinct_models = sorted(
        model for model in set(model_identity_by_player.values()) if model
    )
    missing_model_info = sorted(player for player, model in model_identity_by_player.items() if not model)
    roster_players = {str(entry["player"]) for entry in roster}
    missing_from_roster = sorted(transcript_players - roster_players)
    roster_not_in_transcript = sorted(roster_players - transcript_players)
    passed = len(external_players) >= min_external_participants
    model_diversity_passed = (
        len(distinct_models) >= min_distinct_models
        and not missing_model_info
    )
    status = "passed" if passed else "not_checked"
    if require_external_participants and not passed:
        status = "failed"
    elif roster:
        status = "passed" if passed else "insufficient"
    model_diversity_status = "passed" if model_diversity_passed else "not_checked"
    if require_model_diversity and not model_diversity_passed:
        model_diversity_status = "failed"
    elif roster:
        model_diversity_status = "passed" if model_diversity_passed else "insufficient"
    return {
        "status": status,
        "passed": passed,
        "required": require_external_participants,
        "min_external_participants": min_external_participants,
        "external_players": external_players,
        "model_diversity_status": model_diversity_status,
        "model_diversity_passed": model_diversity_passed,
        "model_diversity_required": require_model_diversity,
        "min_distinct_models": min_distinct_models,
        "distinct_external_models": distinct_models,
        "missing_model_info": missing_model_info,
        "missing_from_roster": missing_from_roster,
        "roster_not_in_transcript": roster_not_in_transcript,
        "note": (
            "Participant roster data is operator-supplied evidence. It is not a cryptographic proof, "
            "but it records which scoreboard players were claimed as external AI participants and "
            "whether they represent multiple reported model identities."
        ),
    }


def _load_response_reports(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    root = Path(path)
    if not root.exists():
        raise ValueError(f"response report directory does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"response report path must be a directory: {root}")

    reports: list[dict[str, Any]] = []
    for report_path in sorted(root.glob("*.json")):
        payload = json.loads(report_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"response report must be a JSON object: {report_path}")
        player = str(payload.get("expected_player") or payload.get("player") or "").strip()
        if not player:
            raise ValueError(f"response report is missing player identity: {report_path}")
        reports.append(dict(payload, player=player, report_path=str(report_path)))
    return reports


def _load_round_audits(paths: list[str] | None) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for raw_path in paths or []:
        path = Path(raw_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"round audit must be a JSON object: {path}")
        audits.append(dict(payload, audit_path=str(path)))
    return audits


def _safe_response_report(report: Mapping[str, Any]) -> bool:
    return (
        isinstance(report.get("extracted"), dict)
        and int(report.get("json_objects_found", 0)) == 1
        and report.get("player_matches_expected") is not False
        and report.get("status") not in {"multiple_json_objects", "no_json_object", "player_mismatch"}
    )


def _submission_provenance_evidence(
    records: list[dict[str, Any]],
    roster: list[dict[str, Any]],
    reports: list[dict[str, Any]],
    *,
    response_report_dir: str | Path | None,
    require_response_reports: bool,
) -> dict[str, Any]:
    transcript_players = _players_in_records(records)
    external_players = {
        str(entry["player"])
        for entry in roster
        if entry.get("external") is True and str(entry["player"]) in transcript_players
    }
    required_players = sorted(external_players if external_players else transcript_players)
    reports_by_player: dict[str, dict[str, Any]] = {}
    duplicate_players: list[str] = []
    for report in reports:
        player = str(report["player"])
        if player in reports_by_player:
            duplicate_players.append(player)
            continue
        reports_by_player[player] = report

    machine_checked_players = sorted(
        player
        for player in required_players
        if player in reports_by_player and _safe_response_report(reports_by_player[player])
    )
    contract_clean_players = sorted(
        player
        for player in machine_checked_players
        if reports_by_player[player].get("contract_ok") is True
    )
    missing_reports = sorted(player for player in required_players if player not in reports_by_player)
    unsafe_reports = sorted(
        player
        for player in required_players
        if player in reports_by_player and not _safe_response_report(reports_by_player[player])
    )
    passed = bool(response_report_dir) and not missing_reports and not unsafe_reports and not duplicate_players
    if response_report_dir is None:
        status = "failed" if require_response_reports else "not_checked"
    elif passed:
        status = "passed"
    else:
        status = "failed" if require_response_reports else "incomplete"

    return {
        "status": status,
        "passed": passed,
        "required": require_response_reports,
        "response_report_dir": str(response_report_dir) if response_report_dir else None,
        "required_players": required_players,
        "machine_checked_players": machine_checked_players,
        "contract_clean_players": contract_clean_players,
        "missing_reports": missing_reports,
        "unsafe_reports": unsafe_reports,
        "duplicate_players": sorted(set(duplicate_players)),
        "reports_seen": len(reports),
        "note": (
            "Response reports are deterministic outputs from conjecture_golf.chat_response. "
            "They reduce manual editing ambiguity, but they are still local provenance evidence, "
            "not proof of which remote model produced the text."
        ),
    }


def _round_audit_evidence(
    records: list[dict[str, Any]],
    roster: list[dict[str, Any]],
    audits: list[dict[str, Any]],
    *,
    require_round_audit: bool,
    require_continuation_appeal: bool,
) -> dict[str, Any]:
    transcript_players = _players_in_records(records)
    external_players = sorted(
        str(entry["player"])
        for entry in roster
        if entry.get("external") is True and str(entry["player"]) in transcript_players
    )
    required_players = external_players or sorted(transcript_players)
    audited_players: set[str] = set()
    failed_audits: list[str] = []
    missing_continuation_appeal: list[str] = []
    failed_continuation_appeal: list[str] = []
    for audit in audits:
        metrics = audit.get("metrics") if isinstance(audit.get("metrics"), Mapping) else {}
        audit_name = str(audit.get("audit_path") or audit.get("round_dir") or "unknown")
        for player in metrics.get("expected_players", []) if isinstance(metrics.get("expected_players"), list) else []:
            if isinstance(player, str) and player.strip():
                audited_players.add(player.strip())
        if audit.get("passed") is not True:
            failed_audits.append(audit_name)
        next_pack_appeal = metrics.get("next_pack_ai_appeal")
        if require_continuation_appeal:
            if not isinstance(next_pack_appeal, Mapping):
                missing_continuation_appeal.append(audit_name)
            elif next_pack_appeal.get("passed") is not True:
                failed_continuation_appeal.append(audit_name)

    missing_audited_players = sorted(player for player in required_players if player not in audited_players)
    passed = (
        bool(audits)
        and not failed_audits
        and not missing_audited_players
        and not missing_continuation_appeal
        and not failed_continuation_appeal
    )
    if not audits:
        status = "failed" if require_round_audit else "not_checked"
    elif passed:
        status = "passed"
    else:
        status = "failed" if require_round_audit else "incomplete"
    return {
        "status": status,
        "passed": passed,
        "required": require_round_audit,
        "continuation_appeal_required": require_continuation_appeal,
        "round_audit_files": [str(audit.get("audit_path") or audit.get("round_dir") or "") for audit in audits],
        "audits_seen": len(audits),
        "required_players": required_players,
        "audited_players": sorted(audited_players),
        "missing_audited_players": missing_audited_players,
        "failed_audits": failed_audits,
        "missing_continuation_appeal": missing_continuation_appeal,
        "failed_continuation_appeal": failed_continuation_appeal,
        "note": (
            "Round audits prove that preserved raw external-AI replies passed strict intake, "
            "entered canonical judging, and produced AI-appeal-checked continuation artifacts "
            "before final evidence was bundled."
        ),
    }


def _render_roster_markdown(roster: list[dict[str, Any]]) -> str:
    lines = [
        "# Participant Roster",
        "",
        "| player | external | kind | model | strategy | interface |",
        "| --- | ---: | --- | --- | --- | --- |",
    ]
    for entry in roster:
        lines.append(
            "| "
            f"`{entry.get('player', '')}` | "
            f"{str(entry.get('external') is True).lower()} | "
            f"{entry.get('kind', '')} | "
            f"{entry.get('model', entry.get('model_name', ''))} | "
            f"{entry.get('strategy', '')} | "
            f"{entry.get('interface', '')} |"
        )
    if not roster:
        lines.append("| none | false |  |  |  |  |")
    lines.append("")
    return "\n".join(lines)


def _render_evidence_markdown(summary: dict[str, Any]) -> str:
    audit = summary["closed_test_audit"]
    audit_summary = audit["summary"]
    participant_evidence = summary["participant_evidence"]
    submission_provenance = summary["submission_provenance"]
    round_audit = summary["round_audit_evidence"]
    final_evidence = summary["final_external_evidence"]
    lines = [
        "# Season 0 Evidence Pack",
        "",
        f"Audit passed: `{str(audit['passed']).lower()}`",
        f"External participant evidence: `{participant_evidence['status']}`",
        f"Model diversity: `{participant_evidence['model_diversity_status']}`",
        f"Submission provenance: `{submission_provenance['status']}`",
        f"Round audit evidence: `{round_audit['status']}`",
        f"Final external evidence: `{final_evidence['status']}`",
        f"Transcript: `{summary['transcript']}`",
        "",
        "## Match Evidence",
        "",
        f"- Players: `{len(audit_summary['players'])}`",
        f"- Game moves: `{audit_summary['game_moves']}`",
        f"- Strategic styles: `{', '.join(audit_summary['strategic_styles'])}`",
        f"- Score spread: `{audit_summary['score_spread']}`",
        f"- Moves remaining: `{audit_summary['moves_remaining']}`",
        "",
        "## Participant Evidence",
        "",
        f"- External players in transcript: `{len(participant_evidence['external_players'])}`",
        f"- Required external players: `{participant_evidence['min_external_participants']}`",
        f"- Roster check required: `{str(participant_evidence['required']).lower()}`",
        f"- Model diversity: `{participant_evidence['model_diversity_status']}`",
        f"- Distinct external model identities: `{len(participant_evidence['distinct_external_models'])}`",
        f"- Required distinct model identities: `{participant_evidence['min_distinct_models']}`",
        f"- Missing model info: `{', '.join(participant_evidence['missing_model_info']) or 'none'}`",
        f"- Roster file: `{summary['participant_roster'] or 'none'}`",
        f"- Note: {participant_evidence['note']}",
        "",
        "## Submission Provenance",
        "",
        f"- Response report directory: `{submission_provenance['response_report_dir'] or 'none'}`",
        f"- Reports seen: `{submission_provenance['reports_seen']}`",
        f"- Required response reports: `{str(submission_provenance['required']).lower()}`",
        f"- Machine-checked players: `{len(submission_provenance['machine_checked_players'])}`",
        f"- Strict-contract players: `{len(submission_provenance['contract_clean_players'])}`",
        f"- Missing reports: `{', '.join(submission_provenance['missing_reports']) or 'none'}`",
        f"- Unsafe reports: `{', '.join(submission_provenance['unsafe_reports']) or 'none'}`",
        f"- Duplicate report players: `{', '.join(submission_provenance['duplicate_players']) or 'none'}`",
        f"- Note: {submission_provenance['note']}",
        "",
        "## Round Audit Evidence",
        "",
        f"- Round audit files: `{', '.join(round_audit['round_audit_files']) or 'none'}`",
        f"- Audits seen: `{round_audit['audits_seen']}`",
        f"- Required round audit: `{str(round_audit['required']).lower()}`",
        f"- Audited players: `{len(round_audit['audited_players'])}`",
        f"- Missing audited players: `{', '.join(round_audit['missing_audited_players']) or 'none'}`",
        f"- Failed audits: `{', '.join(round_audit['failed_audits']) or 'none'}`",
        f"- Continuation appeal required: `{str(round_audit['continuation_appeal_required']).lower()}`",
        f"- Missing continuation appeal: `{', '.join(round_audit['missing_continuation_appeal']) or 'none'}`",
        f"- Failed continuation appeal: `{', '.join(round_audit['failed_continuation_appeal']) or 'none'}`",
        f"- Note: {round_audit['note']}",
        "",
        "## Final External Evidence",
        "",
        f"- Final evidence gate required: `{str(final_evidence['required']).lower()}`",
        f"- Final evidence passed: `{str(final_evidence['passed']).lower()}`",
        f"- Closed-test audit: `{str(final_evidence['checks']['closed_test_audit']).lower()}`",
        f"- External participants: `{str(final_evidence['checks']['external_participants']).lower()}`",
        f"- Model diversity: `{str(final_evidence['checks']['model_diversity']).lower()}`",
        f"- Submission provenance: `{str(final_evidence['checks']['submission_provenance']).lower()}`",
        f"- Round audit: `{str(final_evidence['checks']['round_audit']).lower()}`",
        f"- Note: {final_evidence['note']}",
        "",
        "## Audit Checks",
        "",
        "| check | passed | evidence |",
        "| --- | ---: | --- |",
    ]
    for check in audit["checks"]:
        lines.append(f"| `{check['key']}` | {str(check['passed']).lower()} | {check['evidence']} |")
    lines.extend(
        [
            "",
            "## Reproduce Locally",
            "",
            "Run these from this evidence-pack directory with Conjecture Golf installed:",
            "",
        ]
    )
    lines.extend(f"```bash\n{command}\n```" for command in summary["verification_commands"])
    if not audit["passed"]:
        lines.extend(["", "## Not Yet Proven", ""])
        lines.append(
            "This pack is still useful evidence, but it does not prove Season 0 "
            "has enough multi-agent play depth yet."
        )
        for step in audit["next_steps"]:
            lines.append(f"- {step}")
    if summary["participant_evidence"]["required"] and not summary["participant_evidence"]["passed"]:
        lines.extend(["", "## External Participant Gap", ""])
        lines.append(
            "The evidence pack was asked to require external AI participants, but the roster did not "
            "show enough external players that also appear in the transcript."
        )
    if (
        summary["participant_evidence"]["model_diversity_required"]
        and not summary["participant_evidence"]["model_diversity_passed"]
    ):
        lines.extend(["", "## Model Diversity Gap", ""])
        lines.append(
            "The evidence pack was asked to require multiple reported model identities, but the "
            "participant roster did not provide enough distinct model/model_name/model_family values "
            "for external players that appear in the transcript."
        )
    if summary["submission_provenance"]["required"] and not summary["submission_provenance"]["passed"]:
        lines.extend(["", "## Submission Provenance Gap", ""])
        lines.append(
            "The evidence pack was asked to require raw response inspection reports, but not every "
            "required transcript player had a safe machine-checked report."
        )
    if summary["round_audit_evidence"]["required"] and not summary["round_audit_evidence"]["passed"]:
        lines.extend(["", "## Round Audit Gap", ""])
        lines.append(
            "The evidence pack was asked to require external round audits, but not every required "
            "external transcript player was covered by a passed round-audit report with passed "
            "next-pack AI appeal evidence."
        )
    if final_evidence["required"] and not final_evidence["passed"]:
        lines.extend(["", "## Final Evidence Gap", ""])
        lines.append(
            "The final external evidence gate was requested, but at least one required proof "
            "condition is still missing. Do not claim broad AI appeal from this pack yet."
        )
    lines.append("")
    return "\n".join(lines)


def _final_external_evidence(
    audit: dict[str, Any],
    participant_evidence: dict[str, Any],
    submission_provenance: dict[str, Any],
    round_audit_evidence: dict[str, Any],
    *,
    required: bool,
) -> dict[str, Any]:
    checks = {
        "closed_test_audit": audit["passed"] is True,
        "external_participants": participant_evidence["passed"] is True,
        "model_diversity": participant_evidence["model_diversity_passed"] is True,
        "submission_provenance": submission_provenance["passed"] is True,
        "round_audit": round_audit_evidence["passed"] is True,
    }
    passed = all(checks.values())
    status = "passed" if passed else ("failed" if required else "not_required")
    return {
        "status": status,
        "passed": passed,
        "required": required,
        "checks": checks,
        "note": (
            "This is the machine-readable gate for claiming a completed closed external-AI run. "
            "It requires the closed-test audit, external participant roster, reported model "
            "diversity, raw-response provenance, and passed round-audit evidence to all pass."
        ),
    }


def _cmd_evidence(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    final_external_evidence_required = bool(args.final_external_evidence)
    strict_required = args.strict or final_external_evidence_required
    require_external_participants = args.require_external_participants or final_external_evidence_required
    require_model_diversity = args.require_model_diversity or final_external_evidence_required
    require_response_reports = args.require_response_reports or final_external_evidence_required
    require_round_audit = args.require_round_audit or final_external_evidence_required
    require_round_audit_continuation = args.require_round_audit_continuation or final_external_evidence_required
    season = load_optional_compiled_season(args.season)
    records = list(iter_jsonl(args.transcript))
    roster = _load_participant_roster(args.participant_roster)
    response_reports = _load_response_reports(args.response_report_dir)
    round_audits = _load_round_audits(args.round_audits)
    transcript_out = out / "transcript.jsonl"
    _write_jsonl(transcript_out, records)
    season_spec_name = None
    if args.season:
        season_spec_name = "season_spec.json"
        shutil.copyfile(args.season, out / season_spec_name)

    evaluation = evaluate_records(records, season_scoring=True, season=season)
    standings = build_season_standings(records, season_scoring=True, season=season, move_cap=args.move_cap)
    audit = audit_records(
        records,
        season=season,
        min_players=args.min_players,
        min_game_moves=args.min_game_moves,
        min_strategic_styles=args.min_strategic_styles,
        move_cap=args.move_cap,
    )
    frontier = build_frontier_report_from_records(records, season=season)
    (out / "season_eval.md").write_text(render_evaluation_markdown(evaluation), encoding="utf-8")
    _write_json(out / "season_eval.json", evaluation.to_dict())
    (out / "standings.md").write_text(render_standings_markdown(standings), encoding="utf-8")
    _write_json(out / "standings.json", standings.to_dict())
    (out / "frontier.md").write_text(render_frontier_markdown(frontier), encoding="utf-8")
    _write_json(out / "frontier.json", frontier.to_dict())
    (out / "observer_report.md").write_text(
        render_report(records, season_scoring=True, reveal_policy=args.reveal_policy, season=season),
        encoding="utf-8",
    )
    (out / "observer_report.html").write_text(
        render_html_report(records, season_scoring=True, reveal_policy=args.reveal_policy, season=season),
        encoding="utf-8",
    )
    (out / "closed_test_audit.md").write_text(render_audit_markdown(audit), encoding="utf-8")
    _write_json(out / "closed_test_audit.json", audit.to_dict())
    participant_evidence = _participant_evidence(
        records,
        roster,
        min_external_participants=args.min_external_participants,
        require_external_participants=require_external_participants,
        min_distinct_models=args.min_distinct_models,
        require_model_diversity=require_model_diversity,
    )
    submission_provenance = _submission_provenance_evidence(
        records,
        roster,
        response_reports,
        response_report_dir=args.response_report_dir,
        require_response_reports=require_response_reports,
    )
    round_audit_evidence = _round_audit_evidence(
        records,
        roster,
        round_audits,
        require_round_audit=require_round_audit,
        require_continuation_appeal=require_round_audit_continuation,
    )
    roster_name = None
    if roster:
        roster_name = "participant_roster.json"
        _write_json(out / roster_name, {"participants": roster})
        (out / "participant_roster.md").write_text(_render_roster_markdown(roster), encoding="utf-8")
    response_report_dir_name = None
    if response_reports:
        response_report_dir_name = "response_reports"
        response_out = out / response_report_dir_name
        response_out.mkdir(exist_ok=True)
        for index, report in enumerate(response_reports, start=1):
            player = str(report["player"]).replace("/", "_")
            _write_json(response_out / f"{index:02d}-{player}.report.json", report)
    round_audit_names: list[str] = []
    if round_audits:
        round_audit_out = out / "round_audits"
        round_audit_out.mkdir(exist_ok=True)
        for index, audit_payload in enumerate(round_audits, start=1):
            source_name = Path(str(audit_payload.get("audit_path") or f"round-{index}.json")).stem
            filename = f"{index:02d}-{source_name}.json"
            _write_json(round_audit_out / filename, audit_payload)
            round_audit_names.append(f"round_audits/{filename}")

    final_external_evidence = _final_external_evidence(
        audit.to_dict(),
        participant_evidence,
        submission_provenance,
        round_audit_evidence,
        required=final_external_evidence_required,
    )
    summary = {
        "transcript": "transcript.jsonl",
        "season_spec": season_spec_name,
        "participant_roster": roster_name,
        "response_report_dir": response_report_dir_name,
        "round_audits": round_audit_names,
        "participant_evidence": participant_evidence,
        "submission_provenance": submission_provenance,
        "round_audit_evidence": round_audit_evidence,
        "final_external_evidence": final_external_evidence,
        "closed_test_audit": audit.to_dict(),
        "evaluation": evaluation.to_dict(),
        "standings": standings.to_dict(),
        "verification_commands": _evidence_verification_commands(season_spec_name),
        "note": (
            "This is an evidence pack for a closed Season 0 run. Treat broad AI appeal "
            "as unproven unless closed_test_audit.passed is true and the transcript "
            "came from real external AI participants."
        ),
    }
    _write_json(out / "evidence_summary.json", summary)
    (out / "EVIDENCE.md").write_text(_render_evidence_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if strict_required and not audit.passed:
        return 1
    if require_external_participants and not participant_evidence["passed"]:
        return 1
    if require_model_diversity and not participant_evidence["model_diversity_passed"]:
        return 1
    if require_response_reports and not submission_provenance["passed"]:
        return 1
    if require_round_audit and not round_audit_evidence["passed"]:
        return 1
    if final_external_evidence_required and not final_external_evidence["passed"]:
        return 1
    return 0


def _cmd_experiment(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    season = load_optional_compiled_season(args.season)
    agent_names = args.agents or list(DEFAULT_EXPERIMENT_AGENTS)
    known_agents = set(available_agents())
    unknown = sorted(set(agent_names) - known_agents)
    if unknown:
        raise ValueError(f"unknown agents: {unknown}; choose from {sorted(known_agents)}")

    records = list(iter_jsonl(args.source)) if args.source else []
    quarantine_records: list[dict[str, Any]] = []
    initial_path = out / "initial.jsonl"
    _write_jsonl(initial_path, records)

    rounds: list[dict[str, Any]] = []
    for round_index in range(args.rounds):
        round_no = round_index + 1
        round_dir = out / f"round-{round_no:02d}"
        moves_dir = round_dir / "moves"
        moves_dir.mkdir(parents=True, exist_ok=True)
        start_path = round_dir / "start.jsonl"
        _write_jsonl(start_path, records)

        state = replay_records(records, season_scoring=True, season=season)
        for agent_name in agent_names:
            command = next_agent_command(
                agent_name,
                player=f"{agent_name}-agent",
                state=state,
                prior_commands=records,
                turn_index=round_index,
                seed=args.seed,
            )
            _write_json(moves_dir / f"{agent_name}.json", command)

        result = run_closed_match(
            start_path,
            moves_dir,
            prior_quarantine_records=quarantine_records,
            season_scoring=True,
            season=season,
        )
        outputs = write_closed_match_outputs(
            result,
            round_dir,
            season_scoring=True,
            season=season,
            reveal_policy=args.reveal_policy,
        )
        records = result.canonical_records
        quarantine_records = result.quarantine_records
        rounds.append(
            {
                "round": round_no,
                "accepted": result.accepted_count,
                "rejected": result.rejected_count,
                "canonical_records": len(result.canonical_records),
                "quarantine_records": len(result.quarantine_records),
                "outputs": outputs,
            }
        )

    final_transcript = out / "final_transcript.jsonl"
    _write_jsonl(final_transcript, records)
    final_evaluation = evaluate_records(records, season_scoring=True, season=season)
    final_audit = audit_records(records, season=season)
    (out / "season_eval.md").write_text(render_evaluation_markdown(final_evaluation), encoding="utf-8")
    _write_json(out / "season_eval.json", final_evaluation.to_dict())
    (out / "closed_test_audit.md").write_text(render_audit_markdown(final_audit), encoding="utf-8")
    _write_json(out / "closed_test_audit.json", final_audit.to_dict())

    pack_dir = out / "next_match_pack"
    build_match_pack(
        final_transcript,
        pack_dir,
        season_scoring=True,
        reveal_policy=args.reveal_policy,
        season_path=args.season,
        participants=[f"{agent_name}-agent" for agent_name in agent_names],
    )

    summary = {
        "agents": agent_names,
        "rounds": rounds,
        "seed": args.seed,
        "source": args.source,
        "final_transcript": str(final_transcript),
        "next_match_pack": str(pack_dir),
        "evaluation": final_evaluation.to_dict(),
        "closed_test_audit": final_audit.to_dict(),
        "note": (
            "This deterministic local experiment is a rehearsal for external AI play; "
            "it is not proof that external models will find the game compelling."
        ),
    }
    _write_json(out / "experiment_summary.json", summary)
    lines = [
        "# Season 0 Local Experiment",
        "",
        f"Agents: `{', '.join(agent_names)}`",
        f"Rounds: `{args.rounds}`",
        f"Final transcript: `{final_transcript}`",
        f"Next match pack: `{pack_dir}`",
        "",
        "## Round Results",
        "",
        "| round | accepted | rejected | canonical records | quarantine records |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in rounds:
        lines.append(
            f"| {item['round']} | {item['accepted']} | {item['rejected']} | "
            f"{item['canonical_records']} | {item['quarantine_records']} |"
        )
    lines.extend(["", "## Evaluation", ""])
    lines.append(f"- Strategic styles: `{', '.join(final_evaluation.strategic_styles)}`")
    lines.append(f"- Players: `{len(final_evaluation.players)}`")
    lines.append(f"- Score spread: `{final_evaluation.score_spread}`")
    lines.append("")
    (out / "experiment_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote Season 0 local experiment to {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Season 0 local operations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a local Season 0 transcript.")
    init.add_argument("--out", required=True, help="Output transcript path")
    init.add_argument("--source", default="examples/transcripts/basic.jsonl", help="Seed transcript path")
    init.set_defaults(func=_cmd_init)

    pack = subparsers.add_parser("pack", help="Generate a match pack.")
    pack.add_argument("transcript", help="Transcript path")
    pack.add_argument("--out", required=True, help="Output directory")
    pack.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    pack.add_argument("--min-player-interval-seconds", type=int, default=0)
    pack.add_argument("--season", help="Optional data-only season spec path")
    pack.add_argument(
        "--participant",
        action="append",
        dest="participants",
        help="Participant player name or name=strategy. May be repeated.",
    )
    pack.set_defaults(func=_cmd_pack)

    apply = subparsers.add_parser("apply", help="Validate and optionally append a move.")
    apply.add_argument("transcript", help="Transcript path")
    apply.add_argument("move", help="Move JSON path")
    apply.add_argument("--player", help="Override player name")
    apply.add_argument("--append", action="store_true", help="Append when not rejected as invalid")
    apply.add_argument("--min-player-interval-seconds", type=int, default=0)
    apply.add_argument("--season", help="Optional data-only season spec path")
    apply.set_defaults(func=_cmd_apply)

    report = subparsers.add_parser("report", help="Write replay, standings, frontier, observer, and eval reports.")
    report.add_argument("transcript", help="Transcript path")
    report.add_argument("--out", required=True, help="Output report directory")
    report.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    report.add_argument("--season", help="Optional data-only season spec path")
    report.set_defaults(func=_cmd_report)

    round_cmd = subparsers.add_parser("round", help="Judge one external-AI round and generate the next match pack.")
    round_cmd.add_argument("transcript", help="Starting canonical transcript JSONL")
    round_cmd.add_argument("moves_dir", help="Directory containing participant JSON move files")
    round_cmd.add_argument("--out", required=True, help="Output round directory")
    round_cmd.add_argument("--pattern", default="*.json", help="Move file glob within moves_dir")
    round_cmd.add_argument("--prior-quarantine", help="Existing quarantine JSONL to carry invalid strikes forward")
    round_cmd.add_argument("--min-player-interval-seconds", type=int, default=0)
    round_cmd.add_argument("--invalid-strikes-to-disqualify", type=int, default=3)
    round_cmd.add_argument("--move-cap", type=int, default=24)
    round_cmd.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    round_cmd.add_argument("--season", help="Optional data-only season spec path")
    round_cmd.add_argument(
        "--participant",
        action="append",
        dest="participants",
        help="Participant player name or name=strategy for the next match pack. May be repeated.",
    )
    round_cmd.set_defaults(func=_cmd_round)

    raw_round = subparsers.add_parser(
        "raw-round",
        help="Inspect raw external-AI chat replies, judge the round, and generate the next match pack.",
    )
    raw_round.add_argument("transcript", help="Starting canonical transcript JSONL")
    raw_round.add_argument("raw_response_dir", help="Directory containing raw participant response text files")
    raw_round.add_argument("--out", required=True, help="Output round directory")
    raw_round.add_argument("--pattern", default="*.txt", help="Raw response file glob within raw_response_dir")
    raw_round.add_argument(
        "--participant",
        action="append",
        dest="participants",
        help="Participant player name or name=strategy for expected-player checks and next pack. May be repeated.",
    )
    raw_round.add_argument(
        "--participant-roster",
        help="Optional roster JSON to preserve model/interface evidence in the generated evidence handoff.",
    )
    raw_round.add_argument(
        "--allow-extraction",
        action="store_true",
        help="Allow a single JSON object to be salvaged from prose or Markdown contract violations.",
    )
    raw_round.add_argument("--prior-quarantine", help="Existing quarantine JSONL to carry invalid strikes forward")
    raw_round.add_argument("--min-player-interval-seconds", type=int, default=0)
    raw_round.add_argument("--invalid-strikes-to-disqualify", type=int, default=3)
    raw_round.add_argument("--move-cap", type=int, default=24)
    raw_round.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    raw_round.add_argument("--season", help="Optional data-only season spec path")
    raw_round.add_argument(
        "--strict-exit",
        action="store_true",
        help="Return non-zero when any raw response fails intake or any written move is rejected.",
    )
    raw_round.set_defaults(func=_cmd_raw_round)

    round_audit = subparsers.add_parser(
        "round-audit",
        help="Audit a completed raw external-AI round for strict intake and continuation evidence.",
    )
    round_audit.add_argument("round_dir", help="Directory written by season0 raw-round")
    round_audit.add_argument("--min-external-participants", type=int, default=2)
    round_audit.add_argument("--min-distinct-models", type=int, default=1)
    round_audit.add_argument(
        "--require-model-info",
        action="store_true",
        help="Require every external roster entry to include model/model_name/model_family.",
    )
    round_audit.add_argument(
        "--require-next-pack-appeal",
        action="store_true",
        help="Fail unless the generated next_match_pack passes ai-appeal.",
    )
    round_audit.add_argument(
        "--validate-next-pack-packets",
        action="store_true",
        help="Run packet validation while checking next_match_pack ai-appeal.",
    )
    round_audit.add_argument("--write", action="store_true", help="Write external_round_audit.json/md.")
    round_audit.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    round_audit.set_defaults(func=_cmd_round_audit)

    trial_preflight = subparsers.add_parser(
        "trial-preflight",
        help="Check a generated external_trial kit before sending prompts to external AIs.",
    )
    trial_preflight.add_argument("match_pack", help="Generated match-pack directory")
    trial_preflight.add_argument(
        "--allow-existing-responses",
        action="store_true",
        help="Permit expected raw .txt response files to already exist.",
    )
    trial_preflight.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    trial_preflight.set_defaults(func=_cmd_trial_preflight)

    trial_status = subparsers.add_parser(
        "trial-status",
        help="Inspect external-AI prompt sending and raw-response collection status.",
    )
    trial_status.add_argument("match_pack", help="Generated match-pack directory")
    trial_status.add_argument(
        "--require-ready",
        action="store_true",
        help="Return non-zero unless every expected raw response is ready for raw-round.",
    )
    trial_status.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    trial_status.set_defaults(func=_cmd_trial_status)

    ai_appeal = subparsers.add_parser(
        "ai-appeal",
        help="Audit a generated match pack as a local proxy for AI-player appeal.",
    )
    ai_appeal.add_argument("match_pack", help="Generated match-pack directory")
    ai_appeal.add_argument(
        "--validate-packets",
        action="store_true",
        help="Run packet_agent plus submission_check for every player packet.",
    )
    ai_appeal.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    ai_appeal.set_defaults(func=_cmd_ai_appeal)

    evidence = subparsers.add_parser("evidence", help="Bundle a closed-test transcript with reproducible evidence.")
    evidence.add_argument("transcript", help="Final canonical transcript JSONL")
    evidence.add_argument("--out", required=True, help="Output evidence-pack directory")
    evidence.add_argument("--season", help="Optional data-only season spec path")
    evidence.add_argument("--move-cap", type=int, default=24)
    evidence.add_argument("--min-players", type=int, default=4)
    evidence.add_argument("--min-game-moves", type=int, default=8)
    evidence.add_argument("--min-strategic-styles", type=int, default=3)
    evidence.add_argument("--participant-roster", help="Optional JSON roster of claimed external AI participants")
    evidence.add_argument(
        "--response-report-dir",
        help="Optional directory of chat_response JSON reports for raw external-AI replies",
    )
    evidence.add_argument(
        "--round-audit",
        action="append",
        dest="round_audits",
        help="Optional external_round_audit JSON file. May be repeated.",
    )
    evidence.add_argument("--min-external-participants", type=int, default=4)
    evidence.add_argument(
        "--min-distinct-models",
        type=int,
        default=2,
        help="Minimum distinct model/model_name/model_family values required by --require-model-diversity.",
    )
    evidence.add_argument(
        "--require-external-participants",
        action="store_true",
        help="Return non-zero unless the roster shows enough external players in the transcript.",
    )
    evidence.add_argument(
        "--require-model-diversity",
        action="store_true",
        help="Return non-zero unless external roster players in the transcript report enough distinct model identities.",
    )
    evidence.add_argument(
        "--require-response-reports",
        action="store_true",
        help="Return non-zero unless required transcript players have safe chat_response reports.",
    )
    evidence.add_argument(
        "--require-round-audit",
        action="store_true",
        help="Return non-zero unless passed round-audit reports cover required external transcript players.",
    )
    evidence.add_argument(
        "--require-round-audit-continuation",
        action="store_true",
        help="Return non-zero unless round-audit reports include passed next-pack AI appeal evidence.",
    )
    evidence.add_argument(
        "--final-external-evidence",
        action="store_true",
        help=(
            "Require the full final external-AI evidence gate: closed-test audit, external "
            "participants, model diversity, raw-response reports, round-audit evidence, "
            "and AI-appeal-checked continuation."
        ),
    )
    evidence.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    evidence.add_argument("--strict", action="store_true", help="Return non-zero unless the closed-test audit passes.")
    evidence.set_defaults(func=_cmd_evidence)

    experiment = subparsers.add_parser("experiment", help="Run a deterministic multi-round local closed-match rehearsal.")
    experiment.add_argument("--out", required=True, help="Output experiment directory")
    experiment.add_argument("--source", help="Optional seed transcript path. Defaults to an empty transcript.")
    experiment.add_argument("--agent", action="append", dest="agents", choices=available_agents())
    experiment.add_argument("--rounds", type=int, default=2)
    experiment.add_argument("--seed", type=int, default=0)
    experiment.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    experiment.add_argument("--season", help="Optional data-only season spec path")
    experiment.set_defaults(func=_cmd_experiment)

    args = parser.parse_args(argv)
    if getattr(args, "rounds", 1) < 1:
        parser.error("--rounds must be at least 1")
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
