# Season 0 Rules

Season 0 is the frozen local test season for Conjecture Golf.

Do not change these rules while evaluating Season 0 transcripts. If the game
needs a larger world or richer DSL later, make that Season 1.

## Identity

- Season id: `season_0`
- World version: `season_0`
- DSL version: `dsl_0`
- Scoring version: `season_scoring_0`
- Default reveal policy: `redacted`

The public Python verifier and transcript replay are the judge. GitHub Actions,
observer reports, and human commentary are only presentation layers.

## World

The world is a deterministic 5x5 board.

Symbols:

- `.` empty
- `F` flower
- `W` water
- `S` stone

Relations:

- `orthogonal`: up, down, left, right
- `diagonal`: four diagonal neighbors
- `king`: all eight neighboring cells

## Local Evolution

Each cell evolves by the following public priority order:

1. Empty cells become flowers when diagonal water and orthogonal flowers are
   present, unless any stone is in the king-neighborhood.
2. Flowers with at least two neighboring stones wither into empty cells.
3. Empty cells become water when exactly two orthogonal waters touch them and no
   diagonal stone touches them.
4. Water with no orthogonal empty neighbor evaporates.
5. Otherwise the cell stays unchanged.

The verifier computes the after-board. Players submit before-boards only.

## Move Types

Season 0 accepts these JSON command types:

- `conjecture`
- `counterexample`
- `score`

Issue comments and local move files are data only. The engine never executes
submitted text.

## Conjecture DSL

Condition kinds:

- `target_is`
- `exists`
- `not_exists`
- `count_at_least`
- `count_exactly`

Then clause:

- `target_becomes`

Claim kinds:

- `sufficient`: if the conditions hold, the target becomes the symbol.
- `necessary`: if the target becomes the symbol, the conditions must have held.
- `equivalence`: both directions.

Unknown fields are rejected.

## Scoring Summary

Raw verifier scoring rewards true conjectures and valid counterexamples.

Season scoring adds progression:

- accepted conjectures cover public local obligations;
- new obligations score;
- stale true conjectures score zero;
- duplicate conjectures are rejected;
- equivalence claims split sufficient and necessary obligation coverage;
- counterexamples score best when they are first, original refutations;
- verifier-revealed and duplicate witnesses are discounted.

Verdicts include `score_components` so agents can inspect why a move scored.

## Redaction Policy

Local operator reports may use full reveal mode.

Public or match-pack reports should default to `redacted`, which hides full
verifier-found witnesses while keeping aggregate score and frontier information.

Players may still submit their own counterexample before-boards as public moves.

## Replay Authority

A transcript is a JSONL file. Replaying the same transcript with the same public
code must produce the same verdicts and scores.

The transcript plus repository source is the final authority for Season 0.

## Explicit Non-Goals

Do not add these during Season 0:

- new symbols;
- larger boards;
- larger neighborhoods;
- new relations;
- new condition kinds;
- new claim kinds;
- commit-reveal;
- external AI API calls from the game engine;
- dynamic web app;
- hidden secrets;
- arbitrary code execution from comments, transcripts, or submissions.
