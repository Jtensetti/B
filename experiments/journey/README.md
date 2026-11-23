# The journey trial: from an empty file through four changes

This experiment measures the long-term goal in [the vision](../../docs/vision.md). Can a model, starting from an empty directory, build a real program with libraries from two ecosystems in B, and carry it through changes, with fewer wrong results and less total work than in typed Python?

## Design

- **Task.** A command-line dependency resolver ([steps](steps/)). It reads a JSON manifest and chooses the highest available version allowed by npm's semver rules. In later steps it suggests spellings for unknown packages (edit distance), honors pins, never picks prereleases through a range, and reports a summary. The specification names the npm `semver` package's semantics, as real tooling around npm must.
- **Libraries.** The B program can use Python's standard library and the npm packages `semver` and `fastest-levenshtein`, which are installed in each workspace. The Python program can use the standard library, and may call the same npm packages through `node` if it chooses.
- **Solvers.** Four instances of the same model (Claude Sonnet, through Claude Code subagents), two per language, each in its own empty workspace. B solvers learn B from its documentation during the trial, which is part of B's cost. Steps arrive one at a time in the same conversation. A solver may ask one question per step.
- **Hidden tests.** 20 fixtures, graded after each step against an oracle that uses the npm libraries the specification names. Inputs for steps 1–2 carry no pins. Solvers never see hidden results. They test with their own inputs.
- **Work.** For each step: the solver's tokens, tool calls and wall time as reported by the agent runtime.
