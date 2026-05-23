"""Render a compact turn brief for AI Conjecture Golf players."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from typing import Any

from .replay import iter_jsonl, replay_records
from .season_catalog import load_optional_compiled_season
from .season_standings import SeasonStandings, build_season_standings


def _leaderboard_lookup(standings: SeasonStandings) -> dict[str, dict[str, Any]]:
    return {str(row["player"]): row for row in standings.leaderboard}


def _title_opportunities(data: Mapping[str, Any], player: str | None) -> list[dict[str, Any]]:
    if not player:
        return []
    opportunities = []
    for race in data["title_races"]:
        contenders = race["contenders"]
        current = next((contender for contender in contenders if contender["player"] == player), None)
        if current is None:
            continue
        leader = contenders[0] if contenders else None
        opportunities.append(
            {
                "title": race["title"],
                "rank": current["rank"],
                "value": current["value"],
                "leader": race["leader"],
                "leader_value": leader["value"] if leader else None,
                "status": "leading" if current["rank"] == 1 else "contending",
            }
        )
    return opportunities


def _verdict_details(verdict: Any) -> Mapping[str, Any]:
    details = getattr(verdict, "details", None)
    return details if isinstance(details, Mapping) else {}


def _feedback_lesson(verdict: Any) -> str:
    details = _verdict_details(verdict)
    kind = str(getattr(verdict, "kind", ""))
    ok = bool(getattr(verdict, "ok", False))
    basis = details.get("season_score_basis") or details.get("reason")
    if kind == "conjecture" and ok:
        new_obligations = int(details.get("season_new_obligations") or 0)
        if basis == "stale_true_conjecture" or new_obligations == 0:
            return "True but stale; move toward an open frontier row instead of repeating covered territory."
        return f"Strong law: opened {new_obligations} new obligations. Look for adjacent uncovered transitions."
    if kind == "conjecture":
        target_value = details.get("season_target_value")
        if target_value:
            return f"Risky conjecture was refuted; it created a target worth about {target_value} for refuters."
        return "Risky conjecture was refuted; tighten conditions before submitting a broader law."
    if kind == "counterexample" and ok:
        if basis == "novel_first_counterexample":
            return "Strong refutation: original first counterexamples are valuable."
        if basis == "verifier_revealed_counterexample":
            return "Accepted refutation, but it matched the verifier-revealed witness; search for original witnesses."
        if basis in {"already_countered", "duplicate_witness"}:
            return "Stale refutation; choose an uncountered conjecture or a genuinely new witness pattern."
        return "Accepted refutation; keep looking for sharp, low-noise boards."
    if kind == "invalid":
        reason = details.get("reason")
        return (
            f"Invalid move ({reason}); fix protocol before chasing score."
            if reason
            else "Invalid move; fix protocol before chasing score."
        )
    if kind == "hello":
        return "Profile registered; now submit a scoring move."
    if kind == "score":
        return "Score request has no scoring impact; use the standings to choose a real move."
    return "No strategic feedback available for this move."


def _recent_feedback(verdicts: list[Any] | None, player: str | None, *, limit: int = 3) -> list[dict[str, Any]]:
    if not player or not verdicts:
        return []
    feedback = []
    for verdict in reversed(verdicts):
        if getattr(verdict, "player", None) != player:
            continue
        details = _verdict_details(verdict)
        feedback.append(
            {
                "kind": getattr(verdict, "kind", None),
                "ok": bool(getattr(verdict, "ok", False)),
                "score_delta": int(getattr(verdict, "score_delta", 0)),
                "score_basis": details.get("season_score_basis") or details.get("reason"),
                "lesson": _feedback_lesson(verdict),
            }
        )
        if len(feedback) >= limit:
            break
    return feedback


def build_agent_brief(
    standings: SeasonStandings,
    *,
    player: str | None = None,
    recent_verdicts: list[Any] | None = None,
) -> dict[str, Any]:
    data = standings.to_dict()
    leaderboard = data["leaderboard"]
    leader = leaderboard[0] if leaderboard else None
    player_rows = _leaderboard_lookup(standings)
    player_row = player_rows.get(player) if player else None
    title_opportunities = _title_opportunities(data, player)

    live_titles = []
    for race in data["title_races"]:
        contenders = race["contenders"]
        live_titles.append(
            {
                "title": race["title"],
                "leader": race["leader"],
                "value": race["value"],
                "contenders": [contender["player"] for contender in contenders],
                "is_contested": len(contenders) > 1,
            }
        )

    recommendations = list(data["next_objectives"])
    if player and player in data["unqualified_players"]:
        recommendations.insert(0, "Qualify for title races with one valid conjecture or valid counterexample.")
    elif player and title_opportunities:
        leading = [race for race in title_opportunities if race["status"] == "leading"]
        if leading:
            titles = ", ".join(race["title"] for race in leading[:2])
            recommendations.insert(
                0,
                f"Defend your lead in {titles} by avoiding stale claims and opening fresh frontier.",
            )
        else:
            best = title_opportunities[0]
            recommendations.insert(
                0,
                f"Your clearest live race is {best['title']} at rank {best['rank']}; leader is `{best['leader']}`.",
            )
    elif player and player_row and leader and player != leader["player"]:
        gap = int(leader["total"]) - int(player_row["total"])
        recommendations.insert(0, f"Close the {gap}-point gap to `{leader['player']}` or chase a secondary title.")
    elif player and player_row and leader and player == leader["player"]:
        recommendations.insert(0, "Defend the lead by avoiding stale claims and opening fresh frontier.")

    return {
        "season_id": data["season_id"],
        "phase": data["phase"],
        "moves_remaining": data["moves_remaining"],
        "season_complete": data["season_complete"],
        "player": player,
        "player_row": player_row,
        "leader": leader,
        "qualified_players": data["qualified_players"],
        "unqualified_players": data["unqualified_players"],
        "live_titles": live_titles,
        "title_opportunities": title_opportunities,
        "recent_feedback": _recent_feedback(recent_verdicts, player),
        "top_open_frontier": data["frontier"]["open_frontier"][:3],
        "stale_traps": data["frontier"]["stale_traps"][:3],
        "recommendations": recommendations[:6],
        "submission_contract": [
            "Output exactly one JSON object.",
            "Use one of: hello, conjecture, counterexample, score.",
            "Prefer a compact conjecture covering new obligations, or a sharp counterexample to a valuable false claim.",
            "Do not include prose around the JSON.",
        ],
    }


def _fmt_player(row: Mapping[str, Any] | None) -> str:
    if not row:
        return "-"
    return f"`{row['player']}` ({row['total']} pts)"


def render_agent_brief_markdown(brief: Mapping[str, Any]) -> str:
    lines = [
        "# Agent Turn Brief",
        "",
        f"Season: `{brief['season_id']}`",
        f"Phase: `{brief['phase']}`",
        f"Moves remaining: `{brief['moves_remaining']}`",
        f"Current leader: {_fmt_player(brief.get('leader'))}",
        "",
    ]
    if brief.get("player"):
        lines.extend(["## Your Status", ""])
        if brief.get("player_row"):
            row = brief["player_row"]
            lines.append(
                f"`{brief['player']}`: `{row['total']}` points, "
                f"`{row['valid_conjectures']}` valid conjectures, "
                f"`{row['valid_counterexamples']}` valid counterexamples."
            )
        else:
            lines.append(f"`{brief['player']}` is not yet on the leaderboard.")
        if brief["player"] in brief["unqualified_players"]:
            lines.append("You are not qualified for title races yet.")
        lines.append("")

    if brief.get("player"):
        lines.extend(["## Recent Feedback", ""])
        recent_feedback = brief.get("recent_feedback", [])
        if recent_feedback:
            lines.extend(["| move | ok | score | feedback |", "| --- | ---: | ---: | --- |"])
            for item in recent_feedback:
                basis = f" `{item['score_basis']}`." if item.get("score_basis") else ""
                lines.append(
                    f"| {item['kind']} | {str(item['ok']).lower()} | {item['score_delta']} | "
                    f"{item['lesson']}{basis} |"
                )
        else:
            lines.append("- No prior move feedback for this player yet.")
        lines.append("")

    lines.extend(["## Best Next Moves", ""])
    for item in brief["recommendations"]:
        lines.append(f"- {item}")

    lines.extend(["", "## Live Titles", "", "| title | leader | contenders |", "| --- | --- | --- |"])
    for race in brief["live_titles"]:
        contenders = ", ".join(f"`{player}`" for player in race["contenders"]) or "-"
        leader = race["leader"] or "-"
        lines.append(f"| {race['title']} | `{leader}` | {contenders} |")

    if brief.get("player"):
        lines.extend(["", "## Your Title Opportunities", ""])
        opportunities = brief.get("title_opportunities", [])
        if opportunities:
            lines.extend(["| title | rank | status | leader |", "| --- | ---: | --- | --- |"])
            for race in opportunities:
                leader = race["leader"] or "-"
                lines.append(f"| {race['title']} | {race['rank']} | {race['status']} | `{leader}` |")
        else:
            lines.append("- No current title-race position; qualify or open a new scoring lane.")

    lines.extend(["", "## Open Frontier", "", "| claim | transition | open obligations |", "| --- | --- | ---: |"])
    for row in brief["top_open_frontier"]:
        lines.append(f"| {row['claim_kind']} | `{row['transition']}` | {row['count']} |")
    if not brief["top_open_frontier"]:
        lines.append("| - | - | 0 |")

    lines.extend(["", "## Avoid", ""])
    if brief["stale_traps"]:
        for row in brief["stale_traps"]:
            lines.append(
                f"- Stale `{row['claim_kind']} {row['transition']}` claims: "
                f"`{row['covered']}` already covered, `{row['uncovered']}` remain."
            )
    else:
        lines.append("- No stale traps identified yet.")

    lines.extend(["", "## Submission Contract", ""])
    for item in brief["submission_contract"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a compact AI turn brief from a transcript.")
    parser.add_argument("path", help="JSONL transcript path")
    parser.add_argument("--player", help="Optional player name for personalized guidance")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")
    parser.add_argument("--min-player-interval-seconds", type=int, default=0)
    parser.add_argument("--no-season-scoring", action="store_true")
    parser.add_argument("--season", help="Optional data-only season spec path")
    parser.add_argument("--move-cap", type=int, default=48)
    args = parser.parse_args(argv)
    season = load_optional_compiled_season(args.season)
    records = list(iter_jsonl(args.path))
    standings = build_season_standings(
        records,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=not args.no_season_scoring,
        season=season,
        move_cap=args.move_cap,
    )
    state = replay_records(
        records,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=not args.no_season_scoring,
        season=season,
    )
    brief = build_agent_brief(
        standings,
        player=args.player,
        recent_verdicts=state.verdicts,
    )
    if args.json:
        print(json.dumps(brief, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_agent_brief_markdown(brief))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
