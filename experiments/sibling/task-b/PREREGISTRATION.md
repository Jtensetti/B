# Pre-registration: sibling task B, payslips

Committed before any solver runs. Results will be added below the line, whatever they are. Shared rules: [DESIGN.md](../DESIGN.md). Languages, run and check commands, protocol and measures are the same as in [task A](../task-a/PREREGISTRATION.md).

## Task

The [build brief](steps/build.md) and [changes 1–5](steps/): monthly payslips from time sheets, needing all five [libraries](libs/). Durations are parsed in Go, rounded to quarter hours in Rust, multiplied by agreement rules in C#, and taxed by a Python withholding table, and contract versions are compared with npm `semver`. A [B reference build](reference/build.bee) passes `b check --strict` and grades 0 wrong.

## What is new since task A

B is at version 0.31. It has named record literals, `upper`, `lower` and `trim`, divisors proved by an enclosing condition, `??` on plain values, and accepts identical `foreign` restatements. These were made after task A to remove friction seen in its transcripts. The guide for models is frozen at this commit. Task A's result stands as measured, and it counts toward the goal's sums unchanged.

## Measures

Six employees' payslips and the rejected list, 7 units per step, 6 steps, 42 units per solver, graded by [grade.py](../grade.py) through the oracle's own `grade` function. Output tokens are measured for each whole run. The oracle-error rule of task A applies. The grader refreshes timestamps and restores a root `bin/`, as fixed during task A.

---

## Results (added after the run)

All 18 solvers finished. Data: [`results/results.json`](results/results.json). Final programs: [`solutions/`](solutions/).

| Language | Wrong units (of 126) | Output tokens | Tokens per solver |
| --- | ---: | ---: | --- |
| **B** | **0** | **180 980** | 45 048 · 39 531 · 96 401 |
| TypeScript | 7 | 195 586 | 55 985 · 68 143 · 71 458 |
| Go | 0 | 196 178 | 112 070 · 49 314 · 34 794 |
| Python | 0 | 199 260 | 41 767 · 78 766 · 78 727 |
| Rust | 0 | 239 828 | 74 026 · 112 060 · 53 742 |
| C# | 0 | 266 049 | 80 425 · 144 465 · 41 159 |

- **Errors:** B 0, equal to the best. TypeScript 3's step-1 program stopped at start-up with an import error, so all 7 units of that step were wrong.
- **Work:** B used the fewest output tokens of the six languages, 0.93 times TypeScript, the next cheapest. The spread within each language is large (35 000–145 000), so one task with three solvers does not separate B from TypeScript, Go and Python.
- **Rule violations:** solvers TypeScript 2, C# 3, Rust 2 and Rust 3 wrote scratch files to the shared `sibB/` folder outside their workspaces. TypeScript 2's files were overwritten by others. None of this changes a snapshot, which holds only the solver's own workspace.

### Goal so far, tasks A and B summed

| Language | Wrong units | Output tokens |
| --- | ---: | ---: |
| TypeScript | 7 | 302 307 |
| Go | 12 | 370 060 |
| C# | 0 | 420 348 |
| Rust | 0 | 452 159 |
| **B** | **0** | **476 511** |
| Python | 0 | 487 984 |

After two of three tasks, condition 2 holds for B (no more errors than the best), and condition 3 does not (B uses more output tokens than TypeScript, Go, C# and Rust).
