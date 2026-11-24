# B: a sibling of the old languages

## Long-term goal

**B is a sibling of Python, C# and JavaScript, not their child.** It speaks its own grammar and borrows its vocabulary from the libraries its relatives already have. A program written in B states its owner's decisions. B derives the code from them, uses existing libraries in any of the three ecosystems, and checks before anything runs that the decisions still hold, including across the borders between the languages.

The goal is reached when a model can start from an empty file and a brief, build something people actually need using libraries from at least two ecosystems, and carry it through a sequence of changes with fewer wrong results and less total work than with typed Python or C# alone. That claim must be measured.

## The sibling principle

Every proposed feature is sorted into one of three kinds before anything is built.

| Kind | Owned by | Examples | Rule |
| --- | --- | --- | --- |
| **Grammar** | B | decisions as source (`example`, `also`, `was`, `keeping`, `like`), questions (`b ask`), dimensions, checks across language borders | Build it in B. It is why B exists. |
| **Vocabulary** | the relatives | unit tables, date arithmetic, time zones, currencies, parsing, HTTP, numerics | Borrow it through an adapter. Never copy it into B. |
| **Core words** | B, kept small | weekdays, the SI base units, `kr` | Built in only if it never changes and almost every program needs it. |

A feature that fits none of these kinds is not built. Vocabulary that B has already copied (parts of the unit table and the calendar functions) shrinks as borrowing covers it.

## Why a sibling can do what neither parent can

Python and C# each check their own code. Neither can see that a Python function measuring in feet receives meters from C#. Neither can treat a library's behavior as a checked fact at upgrade time. B sees every side of the border:

- **Dimensions at the border.** A foreign function is declared once with its units, `foreign aviation.takeoff(Speed[knot]) -> Length[ft]`. B converts at every call and rejects a wrong dimension before the program runs.
- **Decisions about libraries.** An `example` on an imported function becomes a fact checked on every build, so a library upgrade that changes behavior fails visibly.
- **Questions instead of guesses.** When a request leaves a case open, B finds the concrete input and asks, whatever language the implementation lives in.

## Measured so far

Eight trials ([journey](../experiments/journey/README.md), [shipping](../experiments/shipping/README.md), [releases and changes](../experiments/releases/README.md), [ambiguity](../experiments/ambiguity/PREREGISTRATION.md), [upgrade](../experiments/upgrade/PREREGISTRATION.md), [cross-cutting changes](../experiments/crosscut/PREREGISTRATION.md), [long run](../experiments/longrun/PREREGISTRATION.md)), with 34 solver runs, produced no substantive wrong output in either language. B's total output tokens ranged from 0.55 times Python's, when it borrowed an npm library that Python had to reimplement, to 3.6 times, when it had nothing to borrow and the model first had to learn B. In the three latest trials, after the guide for models, the ratio was 1.37, 0.89 and 1.03. The goal is not met.

The ambiguity trial was pre-registered to test B's strongest claim about errors: that `also` and `b ask` prevent wrong readings of ambiguous changes. It failed its kill criterion. Every solver in both languages chose the owner's reading without asking, because a well-factored first build already encoded the analogy the change relied on. B therefore no longer claims to reduce errors in changes. The upgrade trial, also pre-registered, failed in the same way. A library silently began returning prices including VAT. Every solver in both languages noticed it during the next change and corrected it, and none had written a check on the library. With today's models and tasks of this size, "fewer errors" has not been measurable. A third design, cross-cutting changes in an inherited seven-module program, was first run with typed Python alone as a calibration. It produced no substantive errors either, so the B stage was not run. The long-run calibration then took typed Python through a build from an empty file and eight interacting changes. It delivered 0 wrong units out of 1 908. The goal's error criterion cannot be met until a task exists on which careful solvers in typed Python actually deliver wrong results. Choosing a task because Python fails on it would not measure B.

## Milestones

Each milestone has a kill criterion. If it fails, the mechanism stays a standalone tool and the language does not grow.

1. **Units across the border.** Unit-annotated foreign signatures for Python, .NET and npm, plus unit vocabulary borrowed from pint (Python) when it is installed. *Kill:* the annotations cost more lines than the conversion bugs they prevent in a realistic multi-library program.
2. **Decisions about libraries.** `example` and `keeping` on imported functions, checked at build time, with a report when a dependency's behavior changes. *Kill:* foreign evaluation is too slow or too nondeterministic to run on every build.
3. **Records and data.** Records, tables of rows and finite types, so that decisions can be about a booking or an order. Data arrives through borrowed readers (JSON, CSV, HTTP). *Kill:* the type checker grows faster than the code it removes from real programs.
4. **Exact money.** Money as exact decimals at runtime, borrowed from Python's `decimal` or .NET's `decimal`. *Kill:* the boundary cost exceeds the rounding errors it removes.
5. **The journey trial.** A model gets an empty file, a brief and a simulated owner, and builds a program that uses libraries from two ecosystems. Then it carries the program through five changes. The comparison is typed Python, or C#, plus tests. Count wrong results, questions, owner lines, tokens and time. *Kill:* B does not deliver fewer wrong results at comparable total cost. Then B's mechanisms become tools for those languages instead.

## Working protocol

So that the work can continue without check-ins:

1. Take the lowest unfinished milestone. Within it, do the step that unblocks the most of the next one.
2. Sort every new idea into grammar, vocabulary or core words. Borrow vocabulary, and do not copy a library.
3. Finish every step with tests, an honest note of what was not verified, updated docs and a pushed commit.
4. Report negative results as plainly as positive ones. A blocked tool, such as an install that is not permitted, is reported, not worked around.
5. Stop and ask only for decisions that belong to the owner: scope, priorities, or anything that leaves the repository.

## What exists

- **Grammar:** executable changes (`also`, `keeping`, `like`), [precedent questions](precedent-questions.md), [functions from examples](examples.md) with questions, `was`, `domain`, `group`, [dimension checking](units.md), membership tests.
- **Vocabulary through adapters:** typed Python, .NET and npm signatures ([interop](interop.md)), Python source adoption, unit-annotated foreign signatures, units borrowed from pint ([units](units.md#across-language-borders)), and examples of imported functions checked after upgrades ([decisions about libraries](library-examples.md)).
- **Core words, plus copied vocabulary to shrink:** [`know calendar`, `know kalender`, `know physics`, `know currencies`](knowledge.md), and a 127-unit table.

The most relevant measured results are the [hidden-policy experiment](../experiments/decisions/README.md), which compares B's questions with random examples, and the [knowledge comparison](knowledge.md). All experiments are listed in [experiments](experiments.md).

## What B will not claim

- B cannot know what the owner means beyond the cases the program and the answers contain.
- An adapter's signature is an assumption about a library, not a proof of its behavior, until an example checks it.
- Fewer source lines do not by themselves mean fewer tokens or lower cost.
