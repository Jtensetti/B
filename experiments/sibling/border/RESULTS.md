# Boundary checks on the final delivery and payroll programs

B 0.32 caught 6 of 24 upstream faults. Eighteen misses already rule out condition 4. Even catching all nine inventory faults would give 15/33 (45.5%). The registered threshold is 27/33. Task C is pending.

| Language | Catches | Misses | Unresolved A/B | Clean controls accepted | Comment controls accepted | Full-study possible catches |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B | 6 | 18 | 0 | 6/6 | 6/6 | 6–15 |
| Python | 0 | 24 | 0 | 6/6 | 6/6 | 0–9 |
| TypeScript | 0 | 12 | 12 | 3/6 | 3/6 | 0–21 |
| Go | 3 | 21 | 0 | 6/6 | 6/6 | 3–12 |
| Rust | 2 | 22 | 0 | 6/6 | 6/6 | 2–11 |
| C# | 0 | 24 | 0 | 6/6 | 6/6 | 0–9 |

| Fault class | Opportunities per language | B | Python | TypeScript | Go | Rust | C# |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Wrong unit | 6 | 0 | 0 | 0* | 0 | 0 | 0 |
| Wrong currency | 6 | 0 | 0 | 0* | 0 | 0 | 0 |
| Changed behavior | 6 | 0 | 0 | 0* | 0 | 0 | 0 |
| Changed signature | 6 | 6 | 0 | 0* | 3 | 2 | 0 |

\* Three unresolved controls in payroll leave three unresolved opportunities in each TypeScript column of that task. Under the exact registered command and TypeScript 5.9.3, the clean programs use import.meta, iteration over Set/Map, or BigInt literals beyond the compiler's default module or target. These are recorded as unresolved. No extra flags were supplied. All 36 clean programs had zero wrong outputs at step 5 in the published A/B grades. Runtime correctness here uses those archived scores. Both static controls were checked afresh.

The six B signatures failed at the call or foreign declaration. The two other classes of numerical errors and the policy changes still returned values of the expected types. Only signature changes produced attributable diagnostics. A port may keep producing the original output after an upstream change. This experiment credits a checker only when it reports the change.

[Registration](PREREGISTRATION.md) · [Exact edits](seeds.json) · [Per-submission commands, diagnostics, exit codes and tool versions](results/). To reproduce, install the frozen compiler editable from a separate worktree, install the dependencies in [the environment lock](../environment/package-lock.json), put its tsc on PATH, and invoke `python run.py task-a b /absolute/node_modules result.json` from this directory. Repeat for tasks A/B and language codes b, py, ts, go, rs and cs. Each invocation checks all three submissions in fresh workspaces.
