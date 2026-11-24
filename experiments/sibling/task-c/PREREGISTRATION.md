# Pre-registration: sibling task C, reorder suggestions

Committed before any solver runs. Results will be added below the line, whatever they are. Shared rules: [DESIGN.md](../DESIGN.md), including the fixed task set: the goal's conditions 1–3 are judged on tasks A, B and C summed. Languages, run and check commands, protocol and measures are the same as in [task A](../task-a/PREREGISTRATION.md).

## Task

The [build brief](steps/build.md) and [changes 1–5](steps/): weekly reorder suggestions. The build needs four of the five [libraries](libs/): lead times in Go, demand statistics in Rust, pack rounding in C# and calendar helpers in Python. Change 4 adds npm `fastest-levenshtein`. A [B reference build](reference/build.bee) passes `b check --strict` and grades 0 wrong. It was written before B 0.32 and spells out `range` and `ceil` by hand.

## B version

B 0.32 adds the core words `range`, `ceil` and `floor`, whose absence the reference build exposed. The guide for models is frozen at this commit.

## Measures

12 items on each of two days, 2026-03-19 (ISO week 12) and 2026-11-26 (ISO week 48), 24 units per step and 144 per solver, graded by [grade.py](../grade.py) through the oracle's own `grade` function. Each of the five changes alters at least three units. Output tokens are measured for each whole run. The oracle-error rule and the grader fixes of task A apply.
