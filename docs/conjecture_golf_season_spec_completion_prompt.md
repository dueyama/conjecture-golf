# Conjecture Golf: Completion Push via Data-Only Season Specs

Date: 2026-05-14
Audience: Codex working in the Conjecture Golf repository
Goal: move from a hardcoded Season 0 prototype to a durable AI-native game where future seasons can be proposed by AI agents as safe data, reviewed, linted, evaluated, and eventually played.

---

## 0. Strategic decision

We should stop polishing Season 0 as if it were the final product.

Season 0 has done its job: it proves that the core loop can work locally:

```text
AI reads rules/transcript/frontier
AI submits conjecture or counterexample
public deterministic verifier judges
transcript replay is final authority
observer report explains the match
```

The next completion step is not another Season 0 tuning pass. The next completion step is a **Season Definition System**.

The project becomes much more interesting when other AIs can propose new symbolic worlds. That requires a safe, constrained `season_spec.json` format, not arbitrary Python code.

The new target shape is:

```text
Season Designer AI proposes a data-only season spec
Safety Reviewer AI checks determinism and abuse risk
Playability Reviewer AI checks whether the world is trivial or chaotic
Fixed engine lints, compiles, and evaluates the spec
Operator approves one candidate
Player AIs play the approved season
Observer report explains what happened
```

This is the real meta-game. Season 0 should become the calibration fixture and first example spec.

---

## 1. Non-negotiable constraints

Do not violate these.

```text
No arbitrary code execution from season specs.
No Python verifier code submitted by designer agents.
No randomness.
No hidden state.
No player-specific rules.
No time-dependent behavior.
No external AI API calls from the engine.
No GitHub deployment work in this sprint.
No new public Issue protocol in this sprint unless required by docs only.
All results must remain deterministic and locally replayable.
Unknown fields in specs must be rejected, not ignored.
Invalid specs must produce structured errors.
pytest must pass.
```

The fixed engine controls execution. AI-designed seasons are data only.

---

## 2. Immediate sprint objective

Implement **Season Spec v0.1**, a small safe DSL for defining seasons.

This sprint is complete when the repository can do the following:

```bash
python -m conjecture_golf.season_spec lint seasons/season_0.json
python -m conjecture_golf.season_spec metrics seasons/season_0.json --json
python -m conjecture_golf.season_spec render seasons/season_0.json
python -m conjecture_golf.season_spec smoke seasons/season_0.json
python -m pytest -q
```

Optional, if the existing replay/verify architecture can support it without a large rewrite:

```bash
python -m conjecture_golf.verify examples/conjectures/growth_true.json --season seasons/season_0.json --pretty
python -m conjecture_golf.replay examples/transcripts/basic.jsonl --season seasons/season_0.json --season-scoring
```

If full integration is too invasive, implement the season spec engine first and document the remaining adapter work clearly. Do not destabilize the existing Season 0 commands.

---

## 3. Files to add

Add these files.

```text
conjecture_golf/season_spec.py
conjecture_golf/season_engine.py
conjecture_golf/season_metrics.py
conjecture_golf/season_catalog.py

seasons/season_0.json
seasons/candidates/season_1_moss_candidate.json

SEASON_SPEC_SCHEMA.md
SEASON_DESIGNER_GUIDE.md
SEASON_REVIEWER_GUIDE.md
SEASON_SPEC_COMPLETION_NOTES.md

tests/test_season_spec.py
tests/test_season_engine.py
tests/test_season_metrics.py
```

If names conflict with existing modules, choose close names but preserve the concept.

---

## 4. Season Spec v0.1 schema

Implement a strict JSON schema manually in Python. Do not add a heavy dependency unless already used.

A valid v0.1 spec should look like this:

```json
{
  "schema_version": "season-spec-v0.1",
  "season_id": "season_1_moss_candidate",
  "title": "Moss Candidate",
  "summary": "A tiny candidate season with one new symbol and one new local interaction.",
  "designer": "example",
  "board": {
    "width": 5,
    "height": 5
  },
  "symbols": [
    {"id": ".", "name": "empty", "description": "empty cell"},
    {"id": "F", "name": "flower", "description": "flower"},
    {"id": "W", "name": "water", "description": "water"},
    {"id": "S", "name": "stone", "description": "stone"},
    {"id": "M", "name": "moss", "description": "moss"}
  ],
  "relations": ["orthogonal", "diagonal", "king"],
  "transition": {
    "default": "stay",
    "rules": [
      {
        "id": "moss_spreads_near_two_stones",
        "priority": 10,
        "when": [
          {"target_is": "."},
          {"count_at_least": {"symbol": "S", "relation": "orthogonal", "n": 2}}
        ],
        "becomes": "M"
      }
    ]
  },
  "conjecture_dsl": {
    "claim_kinds": ["sufficient", "necessary", "equivalence"],
    "condition_kinds": [
      "target_is",
      "exists",
      "not_exists",
      "count_at_least",
      "count_exactly"
    ],
    "max_conditions": 6
  },
  "presentation": {
    "redaction_policy": "redacted",
    "observer_title": "Moss Candidate Arena"
  },
  "limits": {
    "max_symbols": 5,
    "max_rules": 5,
    "max_conditions_per_rule": 6,
    "max_local_neighborhoods": 1953125
  }
}
```

### Required top-level keys

```text
schema_version
season_id
title
summary
designer
board
symbols
relations
transition
conjecture_dsl
presentation
limits
```

Reject unknown top-level keys.

### Board constraints for v0.1

```text
width = 5 only
height = 5 only
```

Do not generalize board sizes yet. Stronger seasons can come later.

### Symbol constraints for v0.1

```text
3 <= number of symbols <= 5
symbol id must be a single printable non-whitespace character
symbol "." is required and is the empty symbol
symbol ids must be unique
symbol names must be nonempty strings
```

Season 1 candidate worlds may add at most one symbol beyond Season 0, but the generic validator can allow up to 5.

### Relation constraints for v0.1

Only allow:

```text
orthogonal
diagonal
king
```

No new geometric relation in this sprint.

### Transition constraints for v0.1

```text
transition.default must be "stay"
1 <= number of transition rules <= 5
priorities must be unique integers
lower priority number or higher priority number must be documented clearly; choose one and test it
rules are evaluated in priority order
first matching rule decides the target cell's next symbol
default stay applies if no rule matches
```

Use the same semantics as the existing `world.py` priority order if possible. If the current project uses a different ordering convention, follow the existing convention and document it.

### Rule constraints

Each rule:

```json
{
  "id": "rule_id",
  "priority": 10,
  "when": [ ...conditions... ],
  "becomes": "F"
}
```

Rules must reject:

```text
unknown fields
empty id
duplicate id
non-integer priority
empty when list
unknown condition kinds
unknown symbols
unknown relations
becomes symbol not in symbols
more than max_conditions_per_rule conditions
```

---

## 5. Supported condition kinds

Use the same condition language as the current conjecture DSL.

### target_is

```json
{"target_is": "."}
```

The center/target cell currently has the given symbol.

### exists

```json
{"exists": {"symbol": "W", "relation": "diagonal"}}
```

At least one neighboring cell in the relation has the given symbol.

### not_exists

```json
{"not_exists": {"symbol": "S", "relation": "king"}}
```

No neighboring cell in the relation has the given symbol.

### count_at_least

```json
{"count_at_least": {"symbol": "S", "relation": "orthogonal", "n": 2}}
```

At least `n` neighboring cells in the relation have the given symbol.

### count_exactly

```json
{"count_exactly": {"symbol": "W", "relation": "orthogonal", "n": 2}}
```

Exactly `n` neighboring cells in the relation have the given symbol.

Do not add `or`, nested groups, arbitrary expressions, arithmetic, regex, or callbacks in v0.1.

---

## 6. Engine behavior

Create a compiled engine from a validated spec.

Suggested API:

```python
@dataclass(frozen=True)
class SeasonSpec:
    ...

@dataclass(frozen=True)
class CompiledSeason:
    spec: SeasonSpec

    def step_board(self, board: list[str]) -> list[str]:
        ...

    def next_symbol_for_cell(self, board: list[str], row: int, col: int) -> str:
        ...

    def evaluate_conditions(self, board: list[str], row: int, col: int, conditions: list[dict]) -> bool:
        ...
```

Keep board validation strict and reusable.

Important: this engine must be deterministic and must not mutate inputs.

---

## 7. Season 0 as a spec

Backfill the current hardcoded Season 0 rules as:

```text
seasons/season_0.json
```

It should represent the current local evolution rules as closely as possible:

```text
1. Empty cells become flowers when diagonal water and orthogonal flowers are present, unless any stone is in the king-neighborhood.
2. Flowers with at least two neighboring stones wither into empty cells.
3. Empty cells become water when exactly two orthogonal waters touch them and no diagonal stone touches them.
4. Water trapped by having no orthogonal empty cells evaporates.
5. Otherwise the cell stays unchanged.
```

These should be representable with the v0.1 condition kinds:

```text
target_is
exists
not_exists
count_at_least
count_exactly
```

For water evaporation, use:

```json
{"target_is": "W"},
{"not_exists": {"symbol": ".", "relation": "orthogonal"}}
```

Do not remove the existing hardcoded Season 0 path yet. Add a test proving the spec engine and current `world.py` produce the same next board on a set of representative boards, and ideally on all local 3x3 neighborhoods if feasible within test time.

---

## 8. Metrics for candidate seasons

Implement:

```bash
python -m conjecture_golf.season_spec metrics seasons/candidates/season_1_moss_candidate.json
python -m conjecture_golf.season_spec metrics seasons/candidates/season_1_moss_candidate.json --json
```

Metrics should be deterministic and machine-readable.

Include at least:

```text
schema_valid
symbol_count
rule_count
condition_count_total
condition_count_by_kind
local_neighborhood_count
transition_counts_by_before_after
rule_hit_counts
stay_ratio
change_ratio
symbols_that_can_appear_as_after
symbols_that_never_appear_as_after
symbols_that_never_change
priority_shadow_warnings
readability_score
tractability_status
```

### Readability score

Keep simple. For example:

```text
100
- 5 * extra_symbols_beyond_4
- 3 * rules_beyond_3
- 1 * total_conditions
- 5 * number_of_priority_shadow_warnings
```

Do not pretend this is a true fun metric. It is a linting signal.

### Tractability status

Compute:

```text
symbol_count ** 9
```

For v0.1, reject or warn if this exceeds `max_local_neighborhoods`.

With 5 symbols, this is:

```text
5^9 = 1,953,125
```

This is the v0.1 upper bound.

---

## 9. Season spec linter

Implement structured lint verdicts.

Suggested output:

```json
{
  "ok": true,
  "errors": [],
  "warnings": [
    {
      "code": "LOW_CHANGE_RATIO",
      "message": "Only 1.2% of local neighborhoods change. This season may be too static."
    }
  ],
  "metrics": {...}
}
```

The linter should distinguish:

```text
errors = spec cannot be compiled or safely played
warnings = spec is valid but may be boring, trivial, unreadable, or expensive
```

Hard errors should include:

```text
UNKNOWN_FIELD
MISSING_REQUIRED_FIELD
INVALID_SCHEMA_VERSION
INVALID_BOARD_SIZE
INVALID_SYMBOL
DUPLICATE_SYMBOL
MISSING_EMPTY_SYMBOL
INVALID_RELATION
INVALID_RULE
DUPLICATE_RULE_ID
DUPLICATE_PRIORITY
UNKNOWN_CONDITION_KIND
UNKNOWN_CONDITION_SYMBOL
UNKNOWN_CONDITION_RELATION
UNKNOWN_BECOMES_SYMBOL
TOO_MANY_SYMBOLS
TOO_MANY_RULES
TOO_MANY_CONDITIONS
TOO_MANY_LOCAL_NEIGHBORHOODS
```

Warnings should include:

```text
LOW_CHANGE_RATIO
HIGH_CHANGE_RATIO
UNUSED_SYMBOL
SYMBOL_NEVER_APPEARS
RULE_NEVER_HITS
POSSIBLE_PRIORITY_SHADOWING
VERY_LOW_READABILITY
TRIVIAL_ALL_STAY
```

---

## 10. Render command

Implement:

```bash
python -m conjecture_golf.season_spec render seasons/candidates/season_1_moss_candidate.json
```

Output a human-readable Markdown summary:

```text
# Season: Moss Candidate

Symbols
Relations
Priority rules
Default behavior
Limits
Metrics summary
Warnings
```

This is important because humans need to understand AI-designed worlds.

---

## 11. Smoke command

Implement:

```bash
python -m conjecture_golf.season_spec smoke seasons/candidates/season_1_moss_candidate.json
```

The smoke command should:

1. lint the spec;
2. compile it;
3. run metrics;
4. step several example boards;
5. print a short deterministic report;
6. exit nonzero only for hard errors.

---

## 12. Candidate Season 1 example

Add one candidate example, but do not overfit it.

```text
seasons/candidates/season_1_moss_candidate.json
```

Constraints:

```text
board remains 5x5
symbols are `.`, `F`, `W`, `S`, `M`
relations are existing orthogonal/diagonal/king
add only 1 or 2 rules beyond Season 0-like behavior
keep it readable
```

Example idea:

```text
M = moss
Moss appears in empty cells near two orthogonal stones.
Moss suppresses flower growth or turns isolated water into empty.
```

But choose the actual rules based on what is easiest to implement and test.

---

## 13. Designer and reviewer docs

Add `SEASON_DESIGNER_GUIDE.md`.

Audience: AI agents that propose seasons.

It should say:

```text
You are not writing code.
You are writing a constrained JSON season spec.
Your goal is not complexity; your goal is a small readable world with interesting derived laws.
Your spec must pass lint.
Unknown fields are rejected.
Do not add randomness, hidden state, player-specific behavior, time-dependence, or external APIs.
Prefer one new symbol and one or two new local rules.
```

Add `SEASON_REVIEWER_GUIDE.md`.

Audience: AI agents that review proposed seasons.

It should include review roles:

```text
safety-reviewer: rejects execution/determinism/replay risks
playability-reviewer: checks triviality, chaos, exhaustion, readability
observer-critic: asks whether a human can follow the story
operator-reviewer: recommends accept/revise/reject
```

Reviewer output should be data-only too. Example:

```json
{
  "type": "season_review",
  "reviewer": "playability-reviewer",
  "season_id": "season_1_moss_candidate",
  "recommendation": "revise",
  "scores": {
    "safety": 10,
    "determinism": 10,
    "readability": 7,
    "playability": 6,
    "novelty": 5
  },
  "major_concerns": [
    "Moss appears but never disappears, so invariants may dominate."
  ],
  "suggested_changes": [
    "Add one simple disappearance rule for isolated moss."
  ]
}
```

Do not implement a full review game yet. Documentation and examples are enough for this sprint.

---

## 14. Tests to add

Add tests for:

```text
valid season_0 spec loads
valid candidate spec loads
unknown top-level key rejected
unknown rule field rejected
missing required field rejected
invalid board size rejected
too many symbols rejected
missing empty symbol rejected
duplicate symbol rejected
unknown relation rejected
unknown condition kind rejected
unknown condition symbol rejected
unknown becomes symbol rejected
duplicate priorities rejected
spec engine step_board is deterministic
spec engine does not mutate input
season_0 spec agrees with current world.py on representative boards
metrics output is deterministic
metrics flags all-stay trivial specs
render output contains symbols, rules, and warnings
smoke command exits successfully for valid specs
```

Keep tests fast. If exhaustive comparison against `world.py` is too slow, use representative fixtures plus a separate optional check.

---

## 15. Integration path after this sprint

After Season Spec v0.1 is implemented, the next sprint should be:

```text
1. Add --season option to verify/replay/frontier/observer_report where feasible.
2. Allow match_pack to include a season spec.
3. Allow intake to validate moves against the selected season.
4. Create a local Season Design Pack for other AIs.
5. Run one small designer test: 3 AIs propose candidate specs, 2 AIs review them.
6. Operator chooses one approved spec for Season 1.
```

Do not implement GitHub public arena changes before this local season-spec path is stable.

---

## 16. What not to do

Do not do these in this sprint:

```text
Do not add arbitrary Python season plugins.
Do not add a web app.
Do not implement commit-reveal.
Do not open public GitHub alpha.
Do not create a large formal schema language.
Do not add nested boolean logic to the DSL.
Do not increase board size.
Do not add many relations.
Do not replace existing Season 0 commands.
Do not make metrics the judge of fun.
```

The goal is to finish the foundation quickly.

---

## 17. Suggested Codex implementation order

Use this exact order to avoid getting stuck.

### Step A: Data model and validation

Implement `season_spec.py`.

```text
load_season_spec(path)
validate_season_spec(data) -> SeasonSpecValidationResult
compile_season_spec(data) -> SeasonSpec
```

Add tests until validation is strict.

### Step B: Engine

Implement `season_engine.py`.

```text
CompiledSeason.step_board(board)
CompiledSeason.next_symbol_for_cell(board, row, col)
```

Test deterministic behavior.

### Step C: Season 0 spec

Add `seasons/season_0.json` and compare against existing `world.py`.

### Step D: Metrics

Implement `season_metrics.py` and `python -m conjecture_golf.season_spec metrics`.

### Step E: CLI

Implement the `lint`, `metrics`, `render`, and `smoke` subcommands.

### Step F: Docs

Add `SEASON_SPEC_SCHEMA.md`, `SEASON_DESIGNER_GUIDE.md`, and `SEASON_REVIEWER_GUIDE.md`.

### Step G: Candidate example

Add `seasons/candidates/season_1_moss_candidate.json`.

### Step H: Full test pass

Run:

```bash
python -m pytest -q
python -m conjecture_golf.season_spec lint seasons/season_0.json
python -m conjecture_golf.season_spec metrics seasons/season_0.json --json
python -m conjecture_golf.season_spec render seasons/season_0.json
python -m conjecture_golf.season_spec smoke seasons/season_0.json
```

---

## 18. Pasteable Codex prompt

Paste this to Codex:

```text
We are changing direction slightly: Season 0 is not the final product. It is a calibration fixture. The next completion step is to let other AIs define future seasons safely as data.

Implement Season Spec v0.1.

Core requirement:
AI designer agents must be able to propose candidate symbolic worlds as constrained JSON season specs. The fixed Python engine must lint, compile, evaluate, render, and smoke-test those specs. Do not allow arbitrary Python code in specs. Unknown fields must be rejected. Everything must remain deterministic and locally replayable.

Do not implement GitHub public deployment, commit-reveal, or a web app in this sprint.

Add:
- conjecture_golf/season_spec.py
- conjecture_golf/season_engine.py
- conjecture_golf/season_metrics.py
- conjecture_golf/season_catalog.py if useful
- seasons/season_0.json
- seasons/candidates/season_1_moss_candidate.json
- SEASON_SPEC_SCHEMA.md
- SEASON_DESIGNER_GUIDE.md
- SEASON_REVIEWER_GUIDE.md
- tests for validation, engine behavior, metrics, CLI, and season_0 compatibility

Season Spec v0.1 constraints:
- board width and height are 5 only
- symbols: 3 to 5 single-character symbols, must include "."
- relations: orthogonal, diagonal, king only
- transition.default must be "stay"
- 1 to 5 priority rules
- conditions supported: target_is, exists, not_exists, count_at_least, count_exactly
- no nested boolean logic, no randomness, no hidden state, no player-specific behavior, no time-dependence
- max local neighborhoods must stay <= 5^9 = 1,953,125

CLI:
- python -m conjecture_golf.season_spec lint seasons/season_0.json
- python -m conjecture_golf.season_spec metrics seasons/season_0.json --json
- python -m conjecture_golf.season_spec render seasons/season_0.json
- python -m conjecture_golf.season_spec smoke seasons/season_0.json

Backfill Season 0 as seasons/season_0.json using the current world.py semantics. Keep existing Season 0 commands working. Add tests showing the spec engine agrees with world.py on representative boards.

Metrics should include:
- symbol_count
- rule_count
- total condition count
- local_neighborhood_count
- transition_counts_by_before_after
- rule_hit_counts
- stay_ratio
- change_ratio
- symbols that never appear as after
- symbols that never change
- priority shadow warnings
- readability_score
- tractability_status

Docs:
- Explain that designer AIs write JSON specs, not code.
- Explain how safety reviewers and playability reviewers should evaluate proposed seasons.
- Explain that the goal is not maximum complexity, but small readable worlds with interesting derived properties.

Before finishing, run:
python -m pytest -q
python -m conjecture_golf.season_spec lint seasons/season_0.json
python -m conjecture_golf.season_spec metrics seasons/season_0.json --json
python -m conjecture_golf.season_spec render seasons/season_0.json
python -m conjecture_golf.season_spec smoke seasons/season_0.json
```

---

## 19. Acceptance criteria

The sprint is accepted when:

```text
[ ] Season 0 still works.
[ ] Season 0 can be represented as data in seasons/season_0.json.
[ ] A candidate Season 1 can be represented as data.
[ ] Invalid specs are rejected safely.
[ ] Unknown fields are rejected.
[ ] The spec engine can step a board deterministically.
[ ] Season metrics are deterministic and machine-readable.
[ ] A human can read the rendered season summary.
[ ] An AI can read SEASON_DESIGNER_GUIDE.md and propose a compliant season.
[ ] pytest passes.
```

That is the next real completion milestone.

