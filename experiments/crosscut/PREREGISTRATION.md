# Pre-registration: cross-cutting changes in inherited code

Committed before any solver runs. Results will be added below the line, whatever they are.

## Why

Two pre-registered hypotheses about errors have failed ([ambiguity](../ambiguity/PREREGISTRATION.md), [upgrade](../upgrade/PREREGISTRATION.md)). Across six trials, typed Python solvers delivered no wrong results, so B had nothing to reduce. The [four-trial summary](../releases/README.md#summary-of-four-trials) named one situation that has not been tested: changes whose effects reach code the solver does not read. This trial first checks whether that situation produces errors at all, before B is involved. That keeps the task from being designed for B.

## Stage 1: calibration, typed Python only

- **Program.** An [inherited invoicing program](program/) of 169 lines in seven modules: catalog, customers, discounts, VAT per class, invoices with free shipping, and a report for the accountant. It was written before this file and is correct on the hidden fixtures. One duplication is deliberate and realistic: shipping VAT is a literal `0.25` in `invoice.py` instead of a lookup in the VAT table.
- **Changes**, in order and each complete: [1](steps/change1.md) Norwegian customers are invoiced in NOK, while the report stays in SEK. [2](steps/change2.md) Norwegian customers pay Norwegian VAT. [3](steps/change3.md) Catalog prices include Swedish VAT. Each one touches several modules.
- **Solvers.** Three Claude Haiku instances, each with its own copy of the program, the [brief](steps/brief.md) and `sample.json`. One QUESTION per step is allowed, answered from the [oracle](oracle.py).
- **Grading.** 16 hidden orders from six customers and the 4 report fields, 20 units per step, with a tolerance of 0.02 per amount. An invoice is wrong if its currency, its VAT classes or any amount is wrong.

**Decision rule.** If the three Python solvers deliver no wrong unit over the three changes, the error criterion is not measurable on this kind of task either. Stage 2 is then not run, and that is reported. If they deliver at least one wrong unit, stage 2 runs.

## Stage 2 (only if stage 1 finds errors): B

- The same program written in B, translated module by module before stage 2 starts and committed before any B solver runs. Amounts are `Money[SEK]` in records and signatures, which is how B is meant to be written.
- Three B solvers, the same brief, changes, fixtures and grading.
- **H3.** B solvers deliver fewer wrong units than the stage 1 Python solvers, summed over the three changes.
- **Kill criterion.** If B delivers as many wrong units as Python or more, H3 fails, and B no longer claims that dimension types reduce errors in cross-cutting changes.

---

## Results of stage 1 (added after the run)

Three Haiku solvers took the three changes in their own copies of the program. Grader log: [`results/grades.txt`](results/grades.txt). Final programs: [`solutions/`](solutions/).

| Solver | Change 1 | Change 2 | Change 3 |
| --- | --- | --- | --- |
| Python 1 | 0 | 8 | 8 |
| Python 2 | 0 | 0 | 0 |
| Python 3 | 0 | 0 | 0 |

**By the letter of the grading:** 16 wrong units out of 180, all from one solver.

**In substance: no cross-cutting errors.** Every amount, currency and report field was right in all nine change steps. Python 1's 16 units come from one reading of change 2's wording: "An invoice lists a VAT amount for every class on it, even when it is 0." Python 1 listed all three VAT classes on every Norwegian invoice, adding `"books": 0.0` or `"food": 0.0` to invoices without those products. Python 2 and 3 listed only the classes on the invoice, as the oracle does. With zero-valued extra classes ignored, Python 1 has no wrong unit. Every solver found the hard-coded `0.25` for shipping VAT and changed it. Every solver kept the report in SEK while the Norwegian invoices moved to NOK.

**Stage 2 is not run, a deviation from the decision rule.** Under the rule as written, any wrong unit starts stage 2. The only wrong units here come from the wording of change 2, which B solvers would read in the same text, and have nothing to do with what B's dimension types check. A B result on this task could only differ from Python's by how three solvers read one sentence, and that would say nothing about H3. The deviation can only cost B: it removes the one chance this task gave B to score fewer errors. Anyone who disagrees can run stage 2 with the materials in this directory.

### What this means for the goal

Seven trials, 31 solver runs, and three designs aimed at where errors should occur (ambiguous changes, a silent library upgrade, cross-cutting changes in inherited code) produced no substantive errors in typed Python written by Claude Haiku. The error criterion in B's long-term goal cannot be measured with tasks of this size and today's models. Larger programs or another class of task would be needed before B could be shown to reduce errors.
