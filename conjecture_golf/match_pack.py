"""Generate local match packs for closed Season 0 tests."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
from pathlib import Path
from typing import Any

from .ai_appeal import assess_match_pack_ai_appeal, render_ai_appeal_markdown
from .agent_brief import build_agent_brief, render_agent_brief_markdown
from .ai_state import build_ai_state_bundle, build_player_packet
from .frontier import build_frontier_report_from_records, render_frontier_markdown
from .observer_report import render_html_report, render_report
from .replay import iter_jsonl, replay_records
from .season import load_season_manifest
from .season_catalog import load_optional_compiled_season, resolve_season_path
from .season_standings import build_season_standings, render_standings_markdown


WORLD_SUMMARY = """# World Summary

Conjecture Golf Season 0 uses a deterministic 5x5 symbolic board.

Symbols:

- `.` empty
- `F` flower
- `W` water
- `S` stone

The verifier computes the next board from the public rules in `conjecture_golf/world.py`.
Players never provide the after-board for scoring. A move is a JSON command, and
transcript replay is the final authority.
"""


DSL_SUMMARY = """# DSL Summary

Command types:

- `hello`: register a self-reported agent profile for observer commentary.
- `conjecture`: submit a named claim.
- `counterexample`: submit a before-board against a prior conjecture.
- `score`: request the deterministic leaderboard.

Conjecture claim kinds:

- `sufficient`: if the conditions hold, the target becomes the symbol.
- `necessary`: if the target becomes the symbol, the conditions must have held.
- `equivalence`: both directions.

Condition operators:

- `target_is`
- `exists`
- `not_exists`
- `count_at_least`
- `count_exactly`

Relations:

- `orthogonal`
- `diagonal`
- `king`

Unknown fields are rejected by the validator. Issue comments and transcript
records are data only; no submitted text is executed.

Baseline local styles:

- `rule`: cautious true laws.
- `frontier`: high-coverage unexplored laws.
- `characterizer`: necessary and equivalence claims.
- `greedy`: broad claims that may be refuted.
- `counterexample`: first available refutation.
- `original_refuter`: refutation with public alternative boards, not verifier-revealed witnesses.
- `minimalist`: sharpest available refutation.
- `copycat` and `narrow_spam`: stale/duplicate anti-patterns.
"""


CONJECTURE_TEMPLATE: dict[str, Any] = {
    "type": "conjecture",
    "player": "your-agent-name",
    "name": "short_unique_conjecture_name",
    "claim_kind": "sufficient",
    "if": [
        {"target_is": "."},
        {"exists": {"symbol": "W", "relation": "diagonal"}},
    ],
    "then": {"target_becomes": "W"},
}


COUNTEREXAMPLE_TEMPLATE: dict[str, Any] = {
    "type": "counterexample",
    "player": "your-agent-name",
    "against": "prior_conjecture_name",
    "before": [
        ".....",
        ".....",
        ".....",
        ".....",
        ".....",
    ],
}


HELLO_TEMPLATE: dict[str, Any] = {
    "type": "hello",
    "player": "your-agent-name",
    "agent_profile": {
        "kind": "llm_agent",
        "model_family": "unknown",
        "model_name": "unknown",
        "interface": "unknown",
        "autonomy": "human_paste",
        "can_read_repo": True,
        "can_run_tests": False,
        "can_post_to_github": False,
        "notes": "Self-reported profile. This does not affect scoring.",
    },
}


SCORE_TEMPLATE: dict[str, Any] = {"type": "score", "player": "your-agent-name"}

DEFAULT_STRATEGY_SEQUENCE = [
    "frontier",
    "lawwright",
    "refuter",
    "characterizer",
    "clean",
]

STRATEGY_CARDS: dict[str, str] = {
    "frontier": """# Strategy Card: Frontier Explorer

Primary aim:
Cover new frontier that the current transcript has not explained yet.

Read `frontier.md` and `standings.md` before choosing. Prefer a true conjecture
that covers a visible open transition, or a counterexample that changes which
frontier remains valuable.

Avoid:

- repeating an already-covered obvious law;
- submitting a conjecture that is only a narrower copy of a known one;
- ignoring title races when the frontier is nearly tied.
""",
    "lawwright": """# Strategy Card: Lawwright

Primary aim:
Submit a compact true law with good coverage and low complexity.

Read `reference/conjecture_golf/world.py`, `dsl_summary.md`, and `frontier.md`.
Prefer sufficient claims unless you have a clear necessary/equivalence argument.

Avoid:

- broad conditions that miss a stone/water exception;
- verbose rules that cover little;
- duplicate true conjectures.
""",
    "refuter": """# Strategy Card: Refuter

Primary aim:
Find a sharp, original counterexample to a valuable false conjecture.

Read `transcript.jsonl`, `observer_report.md`, and `standings.md`. Prefer a
before-board that is not merely copied from a verifier-revealed witness.

Avoid:

- duplicate witnesses;
- counterexamples against already-dead claims;
- malformed boards or prose outside the JSON.
""",
    "characterizer": """# Strategy Card: Characterizer

Primary aim:
Chase a necessary or equivalence claim that explains why a transition happens.

Read `reference/conjecture_golf/world.py`, `frontier.md`, and existing
conjectures in `transcript.jsonl`. These moves are risky but can make the match
more interesting when they are correct.

Avoid:

- claiming equivalence when only one direction is understood;
- missing a local exception;
- overfitting to one board instead of the public local rule.
""",
    "clean": """# Strategy Card: Clean Play

Primary aim:
Submit a move that is valid, non-duplicate, and tactically useful.

Read `submission_contract.json`, `templates/`, and your `player_briefs/` entry
if present. Prefer a conservative true law or a score request over invalid JSON.

Avoid:

- unknown fields;
- markdown fences;
- player-name drift between rounds;
- cooldown or quarantine mistakes.
""",
    "stale": """# Strategy Card: Stale-Pressure Probe

Primary aim:
Exercise the season scoring pressure around legal but already-covered claims.

This is mainly for packet-loop rehearsals. A stale true conjecture should remain
replayable and canonical, but score poorly because it adds no new obligations.

Avoid:

- malformed JSON;
- duplicate signatures that quarantine instead of testing stale scoring;
- changing player identity between packet and move.
""",
}


AI_ONE_PAGE_QUICKSTART = """# AI One-Page Quickstart

You are playing Conjecture Golf.

Goal:
Submit one useful move.

Read:
1. `transcript.jsonl`
2. `player_packets/<your-player>.json` if present
3. `AI_STATE.json`
4. `MOVE_CANDIDATES.json`
5. `AI_APPEAL_AUDIT.json`
6. `agent_brief.md`
7. `participant_prompts/<your-player>.md` if the operator gave you one
8. `strategy_cards/<your-role>.md` if your participant prompt names one
9. `standings.md`
10. `frontier.md`
11. `observer_report.md`
12. `reference/REFERENCE_FILES.md`
13. `templates/`
14. `SELF_CHECK.md`

Output exactly one JSON object. No prose.

Choose one:

- `hello`: introduce your agent profile if you have not done so yet.
- `conjecture`: propose a compact law that covers new obligations.
- `counterexample`: refute an existing false conjecture with a before-board.

Rules:

- Do not invent syntax.
- Do not use code execution.
- Do not submit a stale duplicate.
- Do not claim capabilities you are not using.
- Prefer compact rules.
- Prefer original counterexamples.
- Your output will be checked by deterministic replay.
"""


PARTICIPANT_PROMPT = """# Participant Prompt

You are an AI player in Conjecture Golf.

You are given a match pack directory. Read these files first:

1. `AI_ONE_PAGE_QUICKSTART.md`
2. `player_packets/<your-player>.json` if present
3. `AI_STATE.json`
4. `MOVE_CANDIDATES.json`
5. `AI_APPEAL_AUDIT.json`
6. `agent_brief.md`
7. `participant_prompts/<your-player>.md` if the operator gave you one
8. `player_briefs/<your-player>.md` if it exists for you
9. `strategy_cards/<your-role>.md` if your participant prompt names one
10. `standings.md`
11. `frontier.md`
12. `dsl_summary.md`
13. `reference/REFERENCE_FILES.md`
14. `templates/`
15. `SELF_CHECK.md`

Task:
Return exactly one JSON object as your move. Do not wrap it in Markdown. Do not
include prose before or after the JSON.

Good moves usually do one of these:

- submit a compact true conjecture that covers fresh frontier;
- submit a sharp counterexample to a valuable false conjecture;
- submit a `hello` profile if this is your first move.

Before answering, check:

- the JSON uses only the documented DSL;
- the `player` value names your agent consistently;
- conjecture names are short and unique;
- no unknown fields are present;
- no code, shell command, or external API call is requested by the move.
"""


SELF_CHECK = """# Submission Self-Check

Use this before returning a move if you can run local Python commands.

Save your candidate as `moves/<your-player>.json`, then run:

```bash
python -m conjecture_golf.submission_check transcript.jsonl moves/<your-player>.json --expected-player <your-player>
```

If `season_spec.json` exists in this match pack, include it:

```bash
python -m conjecture_golf.submission_check transcript.jsonl moves/<your-player>.json --expected-player <your-player> --season season_spec.json
```

For open-arena routing with quarantine state:

```bash
python -m conjecture_golf.submission_check transcript.jsonl moves/<your-player>.json --expected-player <your-player> --quarantine quarantine.jsonl
```

The command does not append your move. It checks the exact JSON contract,
player-name consistency, deterministic verifier outcome, and optional
canonical/quarantine routing.
"""


CHAT_RESPONSE_INTAKE = """# Chat Response Intake

Use this when an external AI can only reply in a chat window.

Save the raw response first:

```text
raw_responses/<player>.txt
```

Then inspect it:

```bash
python -m conjecture_golf.chat_response raw_responses/<player>.txt --expected-player <player> --out moves/<player>.json --report raw_responses/<player>.report.json
```

The strict contract is exactly one JSON object and no prose. If the response has
Markdown fences or explanatory text, the command reports a contract violation
and does not write `moves/<player>.json`.

If the operator deliberately wants to salvage a single JSON object from a
contract-violating response, rerun with `--allow-extraction` and preserve the
raw response plus report in evidence:

```bash
python -m conjecture_golf.chat_response raw_responses/<player>.txt --expected-player <player> --out moves/<player>.json --report raw_responses/<player>.report.json --allow-extraction
```
"""


OPERATOR_JUDGE_CARD = """# Operator Judge Card

Use this card when collecting one JSON move from each AI participant.

Suggested flow:

1. Give the participant this match pack.
2. Ask it to read `PARTICIPANT_PROMPT.md` and return exactly one JSON object.
3. Save the response as `moves/<player>.json`.
   If it came from a chat UI and may include prose, first save the raw response
   as `raw_responses/<player>.txt` and run:

```bash
python -m conjecture_golf.chat_response raw_responses/<player>.txt --expected-player <player> --out moves/<player>.json --report raw_responses/<player>.report.json
```

4. To judge a whole round at once, place all participant JSON files in `moves/`
   and run:

```bash
python -m conjecture_golf.closed_match transcript.jsonl moves --out round-results
```

5. For participant-facing validation without appending:

```bash
python -m conjecture_golf.submission_check transcript.jsonl moves/<player>.json --expected-player <player>
```

6. For one-off operator validation without appending:

```bash
python -m conjecture_golf.intake transcript.jsonl moves/<player>.json
```

7. For open-arena style routing, validate through quarantine-aware gate:

```bash
python -m conjecture_golf.arena_gate transcript.jsonl moves/<player>.json --quarantine quarantine.jsonl
```

8. Append only after the verdict/routing is acceptable for the match format.

The verifier is the judge. Do not manually award points.
"""


REFERENCE_FILES = """# Reference Files

These are read-only copies of the public deterministic engine files most useful
to AI players. They are included so a participant can inspect the rules without
navigating the full repository.

Recommended order:

1. `conjecture_golf/world.py`
2. `conjecture_golf/dsl.py`
3. `conjecture_golf/verify.py`
4. `conjecture_golf/replay.py`
5. `conjecture_golf/obligations.py`

Do not submit patches to these files as a move. A valid move is still exactly
one JSON object.
"""


SUBMISSION_CONTRACT: dict[str, Any] = {
    "format": "exactly_one_json_object",
    "allowed_command_types": ["hello", "conjecture", "counterexample", "score"],
    "forbidden": [
        "markdown_fences",
        "prose_outside_json",
        "unknown_fields",
        "code_execution_requests",
        "external_ai_api_calls",
        "verifier_modifications_for_score",
    ],
    "recommended_files": [
        "AI_ONE_PAGE_QUICKSTART.md",
        "player_packets/<your-player>.json",
        "AI_STATE.json",
        "MOVE_CANDIDATES.json",
        "AI_APPEAL_AUDIT.json",
        "agent_brief.md",
        "participant_prompts/<your-player>.md",
        "player_briefs/<your-player>.md",
        "strategy_cards/<your-role>.md",
        "standings.md",
        "frontier.md",
        "dsl_summary.md",
        "reference/",
        "templates/",
        "SELF_CHECK.md",
    ],
    "validation_commands": [
        "python -m conjecture_golf.chat_response raw_responses/<player>.txt --expected-player <player> --out moves/<player>.json --report raw_responses/<player>.report.json",
        "python -m conjecture_golf.packet_agent player_packets/<player>.json --out moves/<player>.json",
        "python -m conjecture_golf.submission_check transcript.jsonl moves/<player>.json --expected-player <player>",
        "python -m conjecture_golf.closed_match transcript.jsonl moves --out round-results",
        "python -m conjecture_golf.intake transcript.jsonl moves/<player>.json",
        "python -m conjecture_golf.arena_gate transcript.jsonl moves/<player>.json --quarantine quarantine.jsonl",
    ],
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _safe_player_filename(player: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in player).strip("._-")
    return (cleaned or "player")[:80]


def _parse_participant_specs(participants: list[str]) -> list[dict[str, str]]:
    assignments: list[dict[str, str]] = []
    for index, spec in enumerate(participants):
        raw = spec.strip()
        if not raw:
            continue
        player = raw
        strategy = DEFAULT_STRATEGY_SEQUENCE[index % len(DEFAULT_STRATEGY_SEQUENCE)]
        if "=" in raw:
            maybe_player, maybe_strategy = raw.rsplit("=", 1)
            if not maybe_player.strip() or maybe_strategy.strip() not in STRATEGY_CARDS:
                raise ValueError(f"invalid participant strategy {raw!r}; use player=strategy")
            player = maybe_player.strip()
            strategy = maybe_strategy.strip()
        elif ":" in raw:
            maybe_player, maybe_strategy = raw.rsplit(":", 1)
            if maybe_player.strip() and maybe_strategy.strip() in STRATEGY_CARDS:
                player = maybe_player.strip()
                strategy = maybe_strategy.strip()
        if strategy not in STRATEGY_CARDS:
            raise ValueError(f"unknown strategy {strategy!r}; choose from {sorted(STRATEGY_CARDS)}")
        assignments.append({"player": player, "strategy": strategy})
    return assignments


def _participant_prompt(player: str, strategy: str) -> str:
    strategy_path = f"strategy_cards/{strategy}.md"
    return f"""# Participant Prompt: {player}

You are `{player}` in this Conjecture Golf match.
Assigned strategy: `{strategy}`

Read:

1. `AI_ONE_PAGE_QUICKSTART.md`
2. `agent_brief.md`
3. `player_briefs/{_safe_player_filename(player)}.md` if it exists
4. `{strategy_path}`
5. `standings.md`
6. `frontier.md`
7. `observer_report.md`
8. `reference/REFERENCE_FILES.md`
9. `templates/`

Return exactly one JSON object. Do not wrap it in Markdown.

Your JSON must include:

```json
"player": "{player}"
```

Good next moves are usually one of:

- a compact true conjecture covering open frontier;
- a sharp original counterexample to a valuable false conjecture;
- a `hello` profile if you have not introduced yourself yet.

Your strategy card is public guidance, not hidden information and not a special
rule. Use it to make the round more diverse, but keep the JSON valid.

Do not edit source files as your move. Do not include prose outside the JSON.

If you can run local commands, save your candidate JSON and check it with:

```bash
python -m conjecture_golf.submission_check transcript.jsonl moves/{_safe_player_filename(player)}.json --expected-player "{player}" --season season_spec.json
```

If `season_spec.json` is absent, omit the `--season season_spec.json` flag.
"""


def _write_strategy_cards(out_dir: Path) -> dict[str, str]:
    card_dir = out_dir / "strategy_cards"
    card_dir.mkdir(exist_ok=True)
    index: dict[str, str] = {}
    for key, text in sorted(STRATEGY_CARDS.items()):
        name = f"{key}.md"
        (card_dir / name).write_text(text, encoding="utf-8")
        index[key] = f"strategy_cards/{name}"
    _write_json(card_dir / "index.json", index)
    return index


def _write_participant_prompts(
    out_dir: Path,
    assignments: list[dict[str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    prompt_dir = out_dir / "participant_prompts"
    prompt_dir.mkdir(exist_ok=True)
    index: dict[str, str] = {}
    strategies: dict[str, str] = {}
    for assignment in assignments:
        cleaned = assignment["player"]
        strategy = assignment["strategy"]
        stem = _safe_player_filename(cleaned)
        name = f"{stem}.md"
        (prompt_dir / name).write_text(_participant_prompt(cleaned, strategy), encoding="utf-8")
        index[cleaned] = f"participant_prompts/{name}"
        strategies[cleaned] = strategy
    _write_json(prompt_dir / "index.json", index)
    return index, strategies


def _write_participant_roster_template(out_dir: Path, assignments: list[dict[str, str]]) -> str:
    participants = [
        {
            "player": assignment["player"],
            "external": True,
            "kind": "llm_agent",
            "model": "",
            "model_name": "",
            "model_family": "",
            "interface": "",
            "strategy": assignment["strategy"],
            "notes": "Operator-supplied roster evidence for season0 evidence.",
        }
        for assignment in assignments
    ]
    path = out_dir / "participant_roster_template.json"
    _write_json(
        path,
        {
            "schema": "conjecture_golf.participant_roster.v1",
            "participants": participants,
        },
    )
    return "participant_roster_template.json"


def _participant_specs(assignments: list[dict[str, str]]) -> list[str]:
    return [f"{assignment['player']}={assignment['strategy']}" for assignment in assignments]


def _raw_round_command(assignments: list[dict[str, str]], *, season_spec_name: str | None) -> str:
    command = [
        "python",
        "-m",
        "conjecture_golf.season0",
        "raw-round",
        "transcript.jsonl",
        "external_trial/raw_responses",
        "--out",
        "external_trial/round",
        "--participant-roster",
        "external_trial/participant_roster.json",
        "--strict-exit",
    ]
    if season_spec_name:
        command.extend(["--season", season_spec_name])
    for spec in _participant_specs(assignments):
        command.extend(["--participant", spec])
    return " ".join(shlex.quote(part) for part in command)


def _write_external_trial_kit(
    out_dir: Path,
    assignments: list[dict[str, str]],
    *,
    season_spec_name: str | None,
) -> dict[str, str]:
    trial_dir = out_dir / "external_trial"
    raw_dir = trial_dir / "raw_responses"
    prompt_map_dir = trial_dir / "prompt_map"
    raw_dir.mkdir(parents=True, exist_ok=True)
    prompt_map_dir.mkdir(exist_ok=True)

    expected: list[dict[str, str]] = []
    for assignment in assignments:
        player = assignment["player"]
        stem = _safe_player_filename(player)
        expected.append(
            {
                "player": player,
                "strategy": assignment["strategy"],
                "copy_paste_prompt": f"copy_paste_prompts/{stem}.md",
                "participant_prompt": f"participant_prompts/{stem}.md",
                "raw_response": f"external_trial/raw_responses/{stem}.txt",
                "response_report": f"external_trial/round/response_reports/{stem}.report.json",
            }
        )
        (prompt_map_dir / f"{stem}.md").write_text(
            "\n".join(
                [
                    f"# External Trial Slot: {player}",
                    "",
                    f"- Strategy: `{assignment['strategy']}`",
                    f"- Send prompt: `copy_paste_prompts/{stem}.md`",
                    f"- Save raw response as: `external_trial/raw_responses/{stem}.txt`",
                    f"- Expected player in JSON: `{player}`",
                    "",
                    "Do not edit the response before saving it. The raw text is evidence.",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    roster = {
        "schema": "conjecture_golf.participant_roster.v1",
        "participants": [
            {
                "player": assignment["player"],
                "external": True,
                "kind": "llm_agent",
                "model": "",
                "model_name": "",
                "model_family": "",
                "interface": "",
                "strategy": assignment["strategy"],
                "prompt_sent": f"copy_paste_prompts/{_safe_player_filename(assignment['player'])}.md",
                "raw_response": f"external_trial/raw_responses/{_safe_player_filename(assignment['player'])}.txt",
                "notes": "Fill model/model_name/model_family and interface before final evidence.",
            }
            for assignment in assignments
        ],
    }
    _write_json(trial_dir / "participant_roster.json", roster)
    _write_json(trial_dir / "expected_responses.json", {"responses": expected})
    collection_status = {
        "schema": "conjecture_golf.external_trial_status.v1",
        "allowed_statuses": ["not_sent", "sent", "received", "withdrawn"],
        "participants": [
            {
                "player": assignment["player"],
                "status": "not_sent",
                "prompt_sent": f"copy_paste_prompts/{_safe_player_filename(assignment['player'])}.md",
                "raw_response": f"external_trial/raw_responses/{_safe_player_filename(assignment['player'])}.txt",
                "prompt_sent_at": "",
                "response_received_at": "",
                "operator_notes": "",
            }
            for assignment in assignments
        ],
    }
    _write_json(trial_dir / "collection_status.json", collection_status)

    raw_readme = [
        "# Raw Responses",
        "",
        "Save one unedited external-AI chat response per participant here.",
        "Use the exact filenames listed in `external_trial/expected_responses.json`.",
        "",
        "The response must be exactly one JSON object. No Markdown fences and no prose.",
        "",
    ]
    for item in expected:
        raw_readme.append(f"- `{item['raw_response']}` for `{item['player']}`")
    if not expected:
        raw_readme.append("- No participants were assigned in this match pack.")
    (raw_dir / "README.md").write_text("\n".join(raw_readme), encoding="utf-8")

    command = _raw_round_command(assignments, season_spec_name=season_spec_name)
    readme = [
        "# External AI Trial Kit",
        "",
        "Use this folder to run a closed external-AI round without trusting chat prose.",
        "",
        "0. Before sending prompts, run `python -m conjecture_golf.season0 trial-preflight . --json` from the match-pack root.",
        "1. Send each file listed in `copy_paste_prompt` to the corresponding AI participant.",
        "2. Mark the matching `collection_status.json` row as `sent`.",
        "3. Save each unedited raw response at the listed `raw_response` path and mark that row `received`.",
        "4. Fill `model`, `model_name`, `model_family`, and `interface` in `participant_roster.json`.",
        "5. Run `python -m conjecture_golf.season0 trial-status . --require-ready --json`.",
        "6. Run the raw-round command below from the match-pack root.",
        "7. Run `python -m conjecture_golf.season0 round-audit external_trial/round --require-model-info --json`.",
        "8. Run the `evidence_command` printed by raw-round. It should use `--final-external-evidence`.",
        "",
        "```bash",
        command,
        "```",
        "",
        "Do not claim final external evidence until that final evidence command passes.",
        "",
        "## Expected Responses",
        "",
        "| player | strategy | prompt | raw response |",
        "| --- | --- | --- | --- |",
    ]
    for item in expected:
        readme.append(
            f"| `{item['player']}` | `{item['strategy']}` | "
            f"`{item['copy_paste_prompt']}` | `{item['raw_response']}` |"
        )
    if not expected:
        readme.append("| none |  |  |  |")
    readme.append("")
    (trial_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")
    return {
        "directory": "external_trial",
        "readme": "external_trial/README.md",
        "participant_roster": "external_trial/participant_roster.json",
        "expected_responses": "external_trial/expected_responses.json",
        "collection_status": "external_trial/collection_status.json",
        "raw_response_dir": "external_trial/raw_responses",
        "raw_round_command": command,
    }


def _truncate_section(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text.strip()
    return text[:max_chars].rstrip() + "\n\n[truncated for prompt size]"


def _copy_paste_prompt(
    *,
    player: str,
    strategy: str,
    transcript_text: str,
    agent_brief_text: str,
    standings_text: str,
    frontier_text: str,
    player_brief_text: str | None,
) -> str:
    strategy_text = STRATEGY_CARDS[strategy]
    prompt = f"""# Copy-Paste Prompt For External AI: {player}

You are `{player}` playing Conjecture Golf.

Return exactly one JSON object and no prose. Do not use Markdown fences.
Your JSON must include `"player": "{player}"`.

Assigned public strategy: `{strategy}`.

Game summary:
- Conjecture Golf is a deterministic self-judging game.
- You submit one JSON move: `hello`, `conjecture`, `counterexample`, or `score`.
- Good moves either cover new frontier with a compact true law, refute a false
  conjecture with a before-board, or introduce your agent profile if needed.
- Do not invent fields. Do not ask to run code. Do not edit source files.

Valid conjecture shape:

```json
{{
  "type": "conjecture",
  "player": "{player}",
  "name": "short_unique_name",
  "claim_kind": "sufficient",
  "if": [
    {{"target_is": "."}},
    {{"exists": {{"symbol": "W", "relation": "diagonal"}}}}
  ],
  "then": {{"target_becomes": "F"}}
}}
```

Valid counterexample shape:

```json
{{
  "type": "counterexample",
  "player": "{player}",
  "against": "existing_conjecture_name",
  "before": [".....", ".....", "..F..", ".....", "....."]
}}
```

DSL:
- Symbols: `.`, `F`, `W`, `S`.
- Relations: `orthogonal`, `diagonal`, `king`.
- Conditions: `target_is`, `exists`, `not_exists`, `count_at_least`, `count_exactly`.
- Claim kinds: `sufficient`, `necessary`, `equivalence`.

## Strategy Card

{_truncate_section(strategy_text, max_chars=1600)}

## Current Agent Brief

{_truncate_section(agent_brief_text, max_chars=2200)}

## Your Player Brief

{_truncate_section(player_brief_text or "No prior player brief exists for you yet.", max_chars=1800)}

## Standings

{_truncate_section(standings_text, max_chars=1800)}

## Frontier

{_truncate_section(frontier_text, max_chars=1800)}

## Public Transcript

```jsonl
{_truncate_section(transcript_text, max_chars=5000)}
```

Now return exactly one JSON object for `{player}`.
"""
    return prompt


def _write_copy_paste_prompts(
    out_dir: Path,
    assignments: list[dict[str, str]],
    *,
    transcript_text: str,
    agent_brief_text: str,
    standings_text: str,
    frontier_text: str,
) -> dict[str, str]:
    prompt_dir = out_dir / "copy_paste_prompts"
    prompt_dir.mkdir(exist_ok=True)
    index: dict[str, str] = {}
    for assignment in assignments:
        player = assignment["player"]
        strategy = assignment["strategy"]
        stem = _safe_player_filename(player)
        player_brief_path = out_dir / "player_briefs" / f"{stem}.md"
        player_brief_text = player_brief_path.read_text(encoding="utf-8") if player_brief_path.exists() else None
        name = f"{stem}.md"
        (prompt_dir / name).write_text(
            _copy_paste_prompt(
                player=player,
                strategy=strategy,
                transcript_text=transcript_text,
                agent_brief_text=agent_brief_text,
                standings_text=standings_text,
                frontier_text=frontier_text,
                player_brief_text=player_brief_text,
            ),
            encoding="utf-8",
        )
        index[player] = f"copy_paste_prompts/{name}"
    _write_json(prompt_dir / "index.json", index)
    (out_dir / "COPY_PASTE_PROMPTS.md").write_text(
        "\n".join(
            [
                "# Copy-Paste Prompts",
                "",
                "Use these when a participant cannot read the whole match pack directory.",
                "Each file is a self-contained prompt for one assigned player.",
                "",
                "| player | prompt |",
                "| --- | --- |",
                *[f"| `{player}` | `{path}` |" for player, path in sorted(index.items())],
                "",
            ]
        ),
        encoding="utf-8",
    )
    return index


def _write_player_packets(
    out_dir: Path,
    assignments: list[dict[str, str]],
    *,
    ai_state: dict[str, Any],
    move_candidates: dict[str, Any],
) -> dict[str, str]:
    packet_dir = out_dir / "player_packets"
    packet_dir.mkdir(exist_ok=True)
    index: dict[str, str] = {}
    for assignment in assignments:
        player = assignment["player"]
        stem = _safe_player_filename(player)
        name = f"{stem}.json"
        packet = build_player_packet(
            ai_state,
            move_candidates,
            player=player,
            strategy=assignment["strategy"],
        )
        _write_json(packet_dir / name, packet)
        index[player] = f"player_packets/{name}"
    _write_json(packet_dir / "index.json", index)
    return index


def _season_manifest_payload(compiled_season: Any) -> dict[str, Any]:
    if compiled_season is None:
        return load_season_manifest()
    spec = compiled_season.spec
    return {
        "schema_version": spec.schema_version,
        "season_id": spec.season_id,
        "title": spec.title,
        "board_size": spec.width,
        "symbols": list(spec.symbol_ids),
        "relations": list(spec.relations),
        "claim_kinds": list(spec.conjecture_dsl.claim_kinds),
        "condition_kinds": list(spec.conjecture_dsl.condition_kinds),
        "judge": "deterministic_season_spec_engine",
    }


def _copy_reference_sources(repo_root: Path, out_dir: Path) -> None:
    reference_root = out_dir / "reference"
    reference_root.mkdir(exist_ok=True)
    (reference_root / "REFERENCE_FILES.md").write_text(REFERENCE_FILES, encoding="utf-8")
    source_files = [
        "conjecture_golf/world.py",
        "conjecture_golf/dsl.py",
        "conjecture_golf/verify.py",
        "conjecture_golf/replay.py",
        "conjecture_golf/obligations.py",
        "conjecture_golf/frontier.py",
        "conjecture_golf/season_standings.py",
        "conjecture_golf/season_eval.py",
    ]
    for relative in source_files:
        source = repo_root / relative
        if not source.exists():
            continue
        destination = reference_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def build_match_pack(
    transcript_path: str | Path,
    out_dir: str | Path,
    *,
    min_player_interval_seconds: int = 0,
    season_scoring: bool = True,
    reveal_policy: str = "redacted",
    season_path: str | Path | None = None,
    participants: list[str] | None = None,
) -> dict[str, str]:
    transcript_path = Path(transcript_path)
    out_dir = Path(out_dir)
    records = list(iter_jsonl(transcript_path))
    out_dir.mkdir(parents=True, exist_ok=True)
    templates_dir = out_dir / "templates"
    templates_dir.mkdir(exist_ok=True)
    compiled_season = load_optional_compiled_season(season_path)
    resolved_season_path = resolve_season_path(season_path)
    replay_state = replay_records(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=compiled_season,
    )

    transcript_out = out_dir / "transcript.jsonl"
    shutil.copyfile(transcript_path, transcript_out)
    season_spec_name = None
    if resolved_season_path is not None and resolved_season_path.exists():
        season_spec_name = "season_spec.json"
        shutil.copyfile(resolved_season_path, out_dir / season_spec_name)

    repo_root = _repo_root()
    for filename in [
        "AI_PLAYER_GUIDE.md",
        "HUMAN_OBSERVER_GUIDE.md",
        "README.md",
        "SECURITY.md",
        "SEASON0_RULES.md",
        "SEASON0_OPERATOR_RUNBOOK.md",
        "SEASON_SPEC_SCHEMA.md",
        "SEASON_DESIGNER_GUIDE.md",
        "SEASON_REVIEWER_GUIDE.md",
        "season_manifest.json",
    ]:
        source = repo_root / filename
        if source.exists():
            shutil.copyfile(source, out_dir / filename)
    _copy_reference_sources(repo_root, out_dir)

    (out_dir / "AI_ONE_PAGE_QUICKSTART.md").write_text(AI_ONE_PAGE_QUICKSTART, encoding="utf-8")
    (out_dir / "PARTICIPANT_PROMPT.md").write_text(PARTICIPANT_PROMPT, encoding="utf-8")
    (out_dir / "SELF_CHECK.md").write_text(SELF_CHECK, encoding="utf-8")
    (out_dir / "CHAT_RESPONSE_INTAKE.md").write_text(CHAT_RESPONSE_INTAKE, encoding="utf-8")
    (out_dir / "OPERATOR_JUDGE_CARD.md").write_text(OPERATOR_JUDGE_CARD, encoding="utf-8")
    (out_dir / "world_summary.md").write_text(WORLD_SUMMARY, encoding="utf-8")
    (out_dir / "dsl_summary.md").write_text(DSL_SUMMARY, encoding="utf-8")
    _write_json(out_dir / "submission_contract.json", SUBMISSION_CONTRACT)
    strategy_card_index = _write_strategy_cards(out_dir)
    participant_assignments = _parse_participant_specs(participants or [])
    participant_prompt_index, participant_strategy_index = _write_participant_prompts(
        out_dir,
        participant_assignments,
    )
    participant_roster_template = _write_participant_roster_template(out_dir, participant_assignments)
    external_trial = _write_external_trial_kit(
        out_dir,
        participant_assignments,
        season_spec_name=season_spec_name,
    )
    _write_json(templates_dir / "hello.json", HELLO_TEMPLATE)
    _write_json(templates_dir / "conjecture.json", CONJECTURE_TEMPLATE)
    _write_json(templates_dir / "counterexample.json", COUNTEREXAMPLE_TEMPLATE)
    _write_json(templates_dir / "score.json", SCORE_TEMPLATE)

    observer_md = render_report(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        reveal_policy=reveal_policy,
        season=compiled_season,
    )
    observer_html = render_html_report(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        reveal_policy=reveal_policy,
        season=compiled_season,
    )
    (out_dir / "observer_report.md").write_text(observer_md, encoding="utf-8")
    (out_dir / "observer_report.html").write_text(observer_html, encoding="utf-8")

    frontier = build_frontier_report_from_records(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=compiled_season,
    )
    (out_dir / "frontier.md").write_text(
        render_frontier_markdown(
            frontier,
            display_season_id=compiled_season.spec.season_id if compiled_season else None,
        ),
        encoding="utf-8",
    )
    _write_json(out_dir / "frontier.json", frontier.to_dict())
    standings = build_season_standings(
        records,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        season=compiled_season,
    )
    (out_dir / "standings.md").write_text(render_standings_markdown(standings), encoding="utf-8")
    _write_json(out_dir / "standings.json", standings.to_dict())
    ai_state, move_candidates = build_ai_state_bundle(
        records,
        replay_state=replay_state,
        standings=standings,
        frontier=frontier,
        season=compiled_season,
        min_player_interval_seconds=min_player_interval_seconds,
        season_scoring=season_scoring,
        participants=participant_assignments,
    )
    _write_json(out_dir / "AI_STATE.json", ai_state)
    _write_json(out_dir / "MOVE_CANDIDATES.json", move_candidates)
    player_packet_index = _write_player_packets(
        out_dir,
        participant_assignments,
        ai_state=ai_state,
        move_candidates=move_candidates,
    )
    agent_brief = build_agent_brief(standings)
    agent_brief_md = render_agent_brief_markdown(agent_brief)
    (out_dir / "agent_brief.md").write_text(agent_brief_md, encoding="utf-8")
    _write_json(out_dir / "agent_brief.json", agent_brief)
    player_briefs_dir = out_dir / "player_briefs"
    player_briefs_dir.mkdir(exist_ok=True)
    player_brief_index: dict[str, str] = {}
    for row in standings.leaderboard:
        player = str(row["player"])
        stem = _safe_player_filename(player)
        player_brief = build_agent_brief(
            standings,
            player=player,
            recent_verdicts=replay_state.verdicts,
        )
        md_name = f"{stem}.md"
        json_name = f"{stem}.json"
        (player_briefs_dir / md_name).write_text(render_agent_brief_markdown(player_brief), encoding="utf-8")
        _write_json(player_briefs_dir / json_name, player_brief)
        player_brief_index[player] = f"player_briefs/{md_name}"
    _write_json(player_briefs_dir / "index.json", player_brief_index)

    copy_paste_prompt_index = _write_copy_paste_prompts(
        out_dir,
        participant_assignments,
        transcript_text=transcript_out.read_text(encoding="utf-8"),
        agent_brief_text=agent_brief_md,
        standings_text=(out_dir / "standings.md").read_text(encoding="utf-8"),
        frontier_text=(out_dir / "frontier.md").read_text(encoding="utf-8"),
    )

    season_manifest_payload = _season_manifest_payload(compiled_season)
    files = sorted(str(path.relative_to(out_dir)) for path in out_dir.rglob("*") if path.is_file())
    if "manifest.json" not in files:
        files.append("manifest.json")
    manifest = {
        "season": season_manifest_payload,
        "season_id": season_manifest_payload["season_id"],
        "season_spec": season_spec_name,
        "transcript": "transcript.jsonl",
        "season_scoring": season_scoring,
        "min_player_interval_seconds": min_player_interval_seconds,
        "reveal_policy": reveal_policy,
        "participant_prompts": participant_prompt_index,
        "copy_paste_prompts": copy_paste_prompt_index,
        "player_packets": player_packet_index,
        "participant_strategies": participant_strategy_index,
        "participant_roster_template": participant_roster_template,
        "external_trial": external_trial,
        "strategy_cards": strategy_card_index,
        "files": sorted(files),
    }
    _write_json(out_dir / "manifest.json", manifest)
    appeal_report = assess_match_pack_ai_appeal(out_dir)
    _write_json(out_dir / "AI_APPEAL_AUDIT.json", appeal_report.to_dict())
    (out_dir / "AI_APPEAL_AUDIT.md").write_text(render_ai_appeal_markdown(appeal_report), encoding="utf-8")
    manifest["ai_appeal_audit"] = {
        "json": "AI_APPEAL_AUDIT.json",
        "markdown": "AI_APPEAL_AUDIT.md",
        "passed": appeal_report.passed,
        "score": appeal_report.score,
    }
    manifest["files"] = sorted(str(path.relative_to(out_dir)) for path in out_dir.rglob("*") if path.is_file())
    _write_json(out_dir / "manifest.json", manifest)
    return {
        "out_dir": str(out_dir),
        "manifest": str(out_dir / "manifest.json"),
        "transcript": str(transcript_out),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a closed local Season 0 match pack.")
    parser.add_argument("transcript", help="Current JSONL transcript")
    parser.add_argument("--out", required=True, help="Output directory for the match pack")
    parser.add_argument(
        "--min-player-interval-seconds",
        type=int,
        default=0,
        help="Apply the same cooldown rule used by replay.",
    )
    parser.add_argument("--no-season-scoring", action="store_true", help="Render reports without season scoring.")
    parser.add_argument("--reveal-policy", choices=["full", "redacted"], default="redacted")
    parser.add_argument("--season", help="Optional data-only season spec path")
    parser.add_argument(
        "--participant",
        action="append",
        dest="participants",
        help="Participant player name or name=strategy. May be repeated.",
    )
    args = parser.parse_args(argv)
    build_match_pack(
        args.transcript,
        args.out,
        min_player_interval_seconds=args.min_player_interval_seconds,
        season_scoring=not args.no_season_scoring,
        reveal_policy=args.reveal_policy,
        season_path=args.season,
        participants=args.participants,
    )
    print(f"Wrote match pack to {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
