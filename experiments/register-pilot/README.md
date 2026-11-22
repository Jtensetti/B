# Which notation does a B solver choose when editing?

Eight fresh AI solver contexts each edited one B program. Four changed a parcel routing policy and four replaced an animation ramp with a cyclic pulse. Each task started from either nested `if` or a `cases` table. All four routing solvers submitted tables. All four pulse solvers replaced the original branches with an arithmetic formula. Every first submission passed independent acceptance, including the changes that switched notation.

| Task | Starting notation | Accepted on first submission | Notation submitted | Independent behavioral checks per submission |
| --- | --- | ---: | --- | ---: |
| Routing | Nested `if` | 2/2 | 2 tables | 44/44 |
| Routing | `cases` table | 2/2 | 2 tables | 44/44 |
| Pulse | Nested `if` | 2/2 | 2 arithmetic formulas | 79/79 |
| Pulse | `cases` table | 2/2 | 2 arithmetic formulas | 79/79 |

The eight proposed code revisions used eight submissions with public feedback, zero retries and no unsubmitted final edits. Four distinct source texts cover all submissions. All four pulse solutions were byte-for-byte identical. Independent execution of the solvers therefore adds little evidence about the diversity of possible solutions. [Run records and source names](results.json).

## What varied

The starting notation was the only assigned difference within each task. Each pair of starters lowered to identical typed BIR. Every solver could keep the notation, change it, mix both forms, or write straight-line arithmetic. The routing task combined altered bands, exceptions inside bands, and inherited behavior. The pulse task changed all three gain modes and gave enough information to derive a direct expression. Both tasks asked the solver to preserve a function signature, domain and unaffected tag function. [Routing task](routing/TASK.md) · [Pulse task](sampler/TASK.md).

All solvers received the same syntax card, including both branching forms and arithmetic. Each had a fresh context with shared model defaults and instructional isolation in a common host. They could submit up to three candidates. On submission, a wrapper archived the complete source before running the same compiler, interface check and four public behavior examples for both starting notations. Only that wrapper provided execution feedback. A private scorer judged each archived candidate. An unseen failure would count as unresolved if the solver stopped after passing public checks. [Common card](SYNTAX.md) · [Common protocol](PROTOCOL.md).

The compiler package, both tasks, starters and scorer were frozen before dispatch. The SHA-256 of the frozen `score.py` is `1afbd61e96731582caf5cc7efdfe9feef6f2d916809bba171f022899f4a4b455`. The primary metric was the first independently accepted submission. Candidate sizes and public-feedback call counts are secondary records. Other shell activity, internal reasoning, tokens, cost, elapsed time and exact model build were unmeasured.

## Acceptance and controls

For routing, the scorer enumerated all 39 legal codes from −3 through 35 using explicit sets of intended lane memberships. It also checked rejection just outside each end and three inputs to the retained tag function. For the pulse, the scorer used a separately tabulated eight-tick cycle for each gain across all 72 legal frame/gain pairs. It also checked four invalid input pairs and three tag inputs. Both suites checked the original parameter names and types, return type and purity declaration. Passing establishes these finite observations. Other inputs to the unchanged tag function and arbitrary out-of-domain values were not exhaustively examined. [Scorer](score.py).

Two controls removed behavior omitted from the public examples. Removing the override at routing code 31 passed all public checks but scored 43/44 independently. Suppressing the extra phase advance at gain 3 passed all public checks but scored 61/79 independently.

## Interpretation

Solvers used a single-pivot table for an update that reads as ordered routing rules. Every pulse solver discarded the starting branches when the new behavior had a short arithmetic expression. This is evidence of selective uptake under explicit exposure. It leaves the effect of table availability on retries open. Both starting notations allowed tables, every solver saw the card, and every run succeeded at the earliest possible submission. The two selected tasks and one shared model setting also limit generalization.

## Follow-up with tables disabled

We ran four additional fresh solvers after observing the original eight results. All four used the original nested-`if` starters, task descriptions, frozen compiler, budget and independent scorer. Their syntax card described ordinary conditionals and arithmetic. The submission wrapper rejected any parsed decision table before lowering. Valid ordinary programs received exactly the same compiler and example feedback as before. The comparison below uses only the four original solvers assigned the nested-`if` starters. The two sets of records are kept separately. [Table-disabled instructions](availability/PROTOCOL.md) · [Syntax card](availability/SYNTAX.md) · [Gate](availability/ordinary.py) · [Four additional submission records](availability/results.json).

| Task from nested-`if` starter | Table available, original first-pass results | Table disabled, later first-pass results |
| --- | --- | --- |
| Routing | 2/2 chose `cases`, 44/44 checks each | 2/2 used nested `if`, 44/44 checks each |
| Pulse | 2/2 chose arithmetic, 79/79 checks each | 2/2 used arithmetic, 79/79 checks each |

Each condition used four submissions with public feedback and zero retries. Both routing solvers in each condition produced identical source within their condition. The submitted routing files were 255 bytes with tables available and 372 bytes with tables disabled. Every listed pulse submission had identical contents, 253 bytes. The whole-file sizes include the unchanged tag function.

For these specific edits, both settings achieved the same observed first-pass outcome. The four later runs were assigned sequentially without randomization after we saw the first results. The syntax cards necessarily differed, and the routing and pulse tasks each contain only one maintenance request. These data give no estimate of token use, recovery from failure or gains on harder tasks. The next informative comparison would randomize availability on unfamiliar tasks of varied difficulty, including interacting inputs and updates to established code, with regression checks fixed before generation.

## Replay

With B installed, run from the repository root. The replay scripts check the original and later run records, starting-form equivalence, the two omission controls and enforcement of the availability setting. The final command scores one candidate directly.

```sh
python experiments/register-pilot/replay.py
python experiments/register-pilot/availability/replay.py
python experiments/register-pilot/score.py routing experiments/register-pilot/submissions/routing-1.bee
```
