# Decisions in, program out

**Long-term goal.** In B the source of a program is the set of decisions its owner has made: concrete examples, rules, protections and precedents. The compiler derives the code. After every change it guarantees that every recorded decision still holds. It asks exactly the questions the decisions leave open, as concrete inputs with a small set of possible results.

Most languages, including the ones models write best, treat code as the artifact and decisions as comments, tickets or tests kept somewhere else. A change request then forces a model to find the code that implements a decision, rewrite it, and hope the surrounding decisions survive. That is the three-attempt cycle the project started from. B turns it around:

| Today | In B |
| --- | --- |
| Translate a requirement into code, then write a test | State the requirement as an example; the code follows |
| Find and edit the rule that implements a decision | Add one example or one `also` line |
| Regressions are caught if a test happens to exist | Every recorded decision is checked on every compile |
| A model guesses the meaning of an ambiguous request | B finds the input where the meanings part and asks for one value |
| Changing a result silently overwrites it | `was` must state the old value, so stale context fails |

## A related language, not a translation

Think of Python and C# as two branches of a language family. B is a third. It does not speak either one, but it understands much of both because they share ancestry: functions, types, values and errors. BIR, B's typed intermediate form, plays the part of the shared root. The adapters read the "cognates": Python stubs, .NET metadata and npm declarations become typed B signatures without B executing or translating the foreign code. Related languages also have *false friends*. In Python `-7 // 2` is `-4`, while C# integer division `-7 / 2` gives `-3`. The [operator correspondence experiment](../experiments/operator-correspondence/README.md) looks for exactly these cases. B's rule is to treat a foreign word as understood only when its meaning has been checked, and as an assumption otherwise.

A language can also know things its speakers take for granted. A week is Monday to Sunday, and the weekend is Saturday and Sunday. B ships such [knowledge](knowledge.md) as ordinary B declarations. Knowing a word makes a rule that uses it simpler, so the same examples settle sooner.

## What exists (B 0.18–0.22)

1. **Changes as declarations.** `also rule(case) keeping f, g` extends a rule and protects other results. `like (precedent)` requires the new case to behave like an existing one. See [executable changes](executable-changes.md).
2. **Questions from context.** `b ask` compares a new case with the nearest existing one and asks when they still differ. See [precedent questions](precedent-questions.md).
3. **Functions from examples.** `fn ... by examples` derives an ordered rule list from examples. It asks for the input that separates the plausible readings and asks about the domain neighbors of a case only one example supports. It checks `example` facts on every function and requires `was` for a changed result. `domain` names the values an input can take. See [decisions as source](examples.md).

4. **Knowledge.** `know kalender` brings in domains and named groups written in B. A known group is one test for the learner. Units with exact relations are part of the type system, and currencies never mix without a stated rate. See [what B knows](knowledge.md) and [units](units.md).
## Measured so far

The [decision experiment](../experiments/decisions/README.md) hides six policies and lets an oracle answer B's questions. B identifies four of them exactly with 7–13 answers on domains of 14–100 inputs. Random examples in the same number give the exact policy in at most 30% of trials, and need 1.4–2.9 times as many examples to get there. B settles on a wrong rule for an access policy two cases away from the simplest reading, and refuses a per-item price that is not a rule over literals. A requirement change took one or two owner lines and at most one further question. No model or human owner has used these tools yet.

## Milestones toward the goal

Each milestone has a kill criterion. If it fails, the mechanism stays as a tool and the language does not grow.

1. **Owner trials.** Give a model an empty file, a brief and a simulated owner that answers only questions. Compare B (examples plus code) with typed Python plus tests over a sequence of five changes. Count wrong results delivered, questions, owner lines, model tokens and time. *Kill:* B does not deliver fewer wrong results at a comparable total cost.
2. **Coverage beyond neighbors.** B 0.20 asks about a domain neighbor of a single-witness case. Next, find rules several cases away from the simplest reading, such as the staff hours in the access policy, without the tenfold search cost of a wider margin. *Kill:* the question rate doubles without catching more wrong rules in the trials.
3. **Records and tables.** Most real decisions are about records: a booking, an order, a row. Examples and domains should name fields (`booking.day`), and `domain` should become an enforced finite type. *Kill:* the type checker or runtime cost grows faster than the examples it removes.
4. **Richer results.** Let a case return an expression over its inputs (`10 * items`) by searching small affine forms, and let functions defined by examples call other functions. *Kill:* search time or wrong generalizations outweigh the code saved.
5. **Decisions over libraries.** Examples that describe an imported function (Python, .NET, npm) become checked facts about that dependency at upgrade time. *Kill:* foreign evaluation is too slow or too nondeterministic to check on each build.

## What B will not claim

- B cannot know what the owner means beyond the cases the program and the answers contain.
- Fewer source lines do not by themselves mean fewer tokens or lower cost. Every claim needs a measured comparison with a strong conventional baseline.
- A smaller, honest language that wins on one kind of task is better than a large one that wins on none.
