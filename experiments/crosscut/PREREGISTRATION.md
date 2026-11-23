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
