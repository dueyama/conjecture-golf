# Season Spec Completion Notes

Season Spec v0.1 turns future seasons into safe JSON data.

Implemented target:

- lint data-only season specs;
- compile specs into a deterministic local engine;
- compute machine-readable metrics;
- render human-readable summaries;
- smoke-test specs on example boards;
- keep hardcoded Season 0 behavior as the default path;
- allow `--season` integration for local CLIs.

Out of scope:

- arbitrary Python season plugins;
- GitHub public alpha;
- commit-reveal;
- dynamic web app;
- larger boards;
- new relation geometry;
- nested boolean expressions;
- treating metrics as the final judge of fun.

The next practical step is to let several AI agents propose candidate specs,
review them with the reviewer guide, and operator-select one candidate for a
closed Season 1 playtest.
