# Pre-registration: sibling task B, payslips

Committed before any solver runs. Results will be added below the line, whatever they are. Shared rules: [DESIGN.md](../DESIGN.md). Languages, run and check commands, protocol and measures are the same as in [task A](../task-a/PREREGISTRATION.md).

## Task

The [build brief](steps/build.md) and [changes 1–5](steps/): monthly payslips from time sheets, needing all five [libraries](libs/). Durations are parsed in Go, rounded to quarter hours in Rust, multiplied by agreement rules in C#, and taxed by a Python withholding table, and contract versions are compared with npm `semver`. A [B reference build](reference/build.bee) passes `b check --strict` and grades 0 wrong.

## What is new since task A

B is at version 0.31. It has named record literals, `upper`, `lower` and `trim`, divisors proved by an enclosing condition, `??` on plain values, and accepts identical `foreign` restatements. These were made after task A to remove friction seen in its transcripts. The guide for models is frozen at this commit. Task A's result stands as measured, and it counts toward the goal's sums unchanged.

## Measures

Six employees' payslips and the rejected list, 7 units per step, 6 steps, 42 units per solver, graded by [grade.py](../grade.py) through the oracle's own `grade` function. Output tokens are measured for each whole run. The oracle-error rule of task A applies. The grader refreshes timestamps and restores a root `bin/`, as fixed during task A.
