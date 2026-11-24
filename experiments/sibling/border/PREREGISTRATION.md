# Sibling study of faults at library boundaries

## Population and frozen inputs

Use the step-5 submissions for all three solvers in each of the six languages on A, B and C. The [shared design](../DESIGN.md) fixes their native check commands, also listed in [task A](../task-a/PREREGISTRATION.md). Freeze B, its guide and the supplied libraries at `01a91593241803567c35534acbe3e041d4936b11` for this study. Use independent processes and fresh workspaces, keeping the application and any ports exactly as submitted. Supply the task libraries and locked npm dependencies omitted from the archive. Preserve any submitted library edits. A mismatching mutation anchor is unresolved.

The A and B output studies have already been published. This registration precedes running these mutations on any submission. C has no submissions at registration. Partial tables for A/B are allowed. The C reference build never substitutes for a solver.

## Faults

The [manifest](seeds.json) fixes each exact source edit. Apply one edit at a time to the supplied library in the workspace of every solver for that task. All mutants remain valid library source. Ports continue to run against their own copies. An unchanged port earns no credit for detecting an upstream change. The experiment measures detection of upstream drift. It does not measure whether the port's runtime output would change.

| Task | Wrong unit | Wrong currency | Changed behavior | Changed signature |
| --- | --- | --- | --- | --- |
| A, delivery | Road distance in metres | Carrier price in EUR at 10 SEK/EUR | Finnish VAT becomes 20% | Zone requires a priority flag |
| B, payroll | Duration in minutes | Withholding in whole EUR at 10 SEK/EUR | Saturday multiplier becomes 1 | Quarter-hour rounding requires a paid flag |
| C, inventory | Lead times in hours | No monetary boundary | Baltic Steel lead time becomes 19 days | Pack rounding requires an expedited flag |

In the first three columns the observable value changes without a change to its declared primitive type or calling convention. In the fourth column the provider still compiles on its own. Each task contributes three replicas per seed, for **33 opportunities per language** (12 + 12 + 9). No seed, solver or task is removed after seeing a result.

## Controls and decision rule

Use the unmodified program as a negative control and record its published step-5 hidden-fixture score. Also check a version containing a comment-only edit in each distinct provider file touched on that task. Both checks must accept; the clean final program must have zero wrong units. Otherwise all its opportunities are unresolved. Record the control outcomes even when they fail.

Check every mutant with the registered static command in a new process. Do not run the submitted application on a mutant. An accepted mutant is a miss. A nonzero check is a catch only for a diagnostic attributable to the mutation at the boundary. Preserve diagnostics for review. Missing tools, infrastructure failures, timeouts, missing archives, incorrect controls and unclassified failures are unresolved and cannot earn a catch. Never count a failed clean build as detection.

Report catches, misses, unresolved, and controls for each language. Divide by all 33 for the full study. For incomplete evidence report bounds [catches/33, (catches + unresolved)/33], including pending C opportunities. Condition 4 requires at least 27/33 catches for B and strictly fewer catches for every comparator. Declare failure as soon as the upper bound for B is below 27, or cannot exceed a comparator's lower bound. Declare success only when B's lower bound meets the threshold and exceeds every comparator's upper bound. Publish counts per fault class as well. Preserve raw commands, exit status, diagnostics and tool versions.
