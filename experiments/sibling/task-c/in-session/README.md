# Task C, collected inside the coordinating session

This is **not** the collection prescribed by [COLLECTION.md](../COLLECTION.md), which runs each solver in an isolated container from a frozen image and keeps full CLI streams. This run used the same method as tasks A and B: Claude Haiku subagents of the coordinating session, workspaces in a shared scratch directory, and the stepper and grader as they stood at commit `cc787ae`. It is reported so that it is not lost. The owner decides whether it counts toward the goal.

## Departures from a clean run

- A usage limit stopped 16 of the 18 solvers partway. Each was resumed with the same agent and its saved context after the limit reset. No solver was restarted from scratch.
- Between about 17:47 and 17:48 UTC, a merge put B 0.33 into the working tree that the `b` command runs from. B solvers were still working. The working tree was set back to B 0.32 at 17:48:15 and graded under 0.32.
- Several solvers wrote scratch files to the shared `sibC/` directory, outside their workspaces. Some of these files were overwritten by other solvers. Snapshots contain only each solver's own workspace.
- Output tokens are summed from each agent's transcript (`*.output`), as in A and B. No CLI stream files exist for this run.

## Results

| Language | Wrong units (of 432) | Output tokens |
| --- | ---: | ---: |
| Python | 0 | 109 819 |
| C# | 24 | 121 873 |
| Rust | 0 | 134 007 |
| Go | 0 | 137 882 |
| **B** | **0** | **146 789** |
| TypeScript | 0 | 232 949 |

C# 3's step-1 program was wrong for all 24 units. Data: [results.json](results.json), final programs: [solutions/](solutions/).

## Sums over A, B and this C

| Language | Wrong units | Output tokens |
| --- | ---: | ---: |
| Go | 12 | 507 942 |
| TypeScript | 7 | 535 256 |
| C# | 24 | 542 221 |
| Rust | 0 | 586 166 |
| Python | 0 | 597 803 |
| **B** | **0** | **623 300** |

If this run counted, condition 2 would hold, because B's 0 equals the best. Condition 3 would fail, because B used the most output tokens of all six languages.
