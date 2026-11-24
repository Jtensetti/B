# Pre-registration: the long run

Committed before any solver runs. Results will be added below the line, whatever they are.

## Why

B's goal asks for a measured result: from an empty file, with libraries from two ecosystems, through several changes, with fewer errors and less total work than typed Python. Seven trials produced no substantive errors in typed Python, so the error criterion could not be tested. Those trials had at most five steps and rules that barely interacted. This trial follows the goal's own wording more closely: a build from an empty file and **eight changes whose rules interact** (proration by day, a semantic-version rule, coupons counted in calendar months, a trial period, plan changes within a month, reverse-charge VAT, annual plans, a minimum invoice and rounding to whole kronor). As in the [cross-cutting trial](../crosscut/PREREGISTRATION.md), typed Python is calibrated first, so the task is not shaped to make B win.

## Design (fixed now)

- **Task.** Monthly subscription invoices. The [build brief](steps/build.md) and [changes 1–8](steps/) are written out in full, each with the rule stated exactly. Two ecosystems: npm `semver` (installed in every workspace) for change 1, and Python's date handling.
- **Solvers.** Claude Haiku in separate workspaces, one QUESTION per step, answered from the [oracle](oracle.py) in one sentence. Python solvers write typed Python. B solvers read [B for models](../../docs/for-models.md), unchanged from this commit.
- **Grading.** 40 customers over two months (February and March 2026), 66–80 units per step. Each step's input contains only the fields that exist at that step. A unit is a customer in a month. It is wrong if an invoice is missing or should not be there, its currency differs, or an amount is off by more than 0.02. A program that does not run scores every unit wrong. Output tokens are measured as before.
- **Oracle errors.** If every solver in both languages agrees on a value that differs from the oracle, the oracle is checked by hand against the step's text. A confirmed oracle error is fixed, all runs are regraded, and the fix is reported.

## Stage 1: calibration

Three typed-Python solvers take the build and all eight changes. If they deliver no wrong unit over changes 1–8, the error criterion is not measurable on this task either. Stage 2 is not run, and that is reported.

## Stage 2: B (only if stage 1 has wrong units)

Three B solvers take the same build and changes.

- **H4 (errors).** B solvers deliver fewer wrong units than the Python solvers, summed over changes 1–8.
- **H5 (work).** B solvers use fewer output tokens in total, build and changes together.
- **Kill criterion.** If H4 fails, B no longer claims to reduce errors in long change sequences. The goal counts as met by this trial only if both H4 and H5 hold.

---

## Results of stage 1 (added after the run)

Three typed-Python Haiku solvers built the program from an empty workspace and took all eight changes. Grader log: [`results/grades.txt`](results/grades.txt). Final programs: [`solutions/`](solutions/), 251–294 lines each.

**Every solver delivered 0 wrong units at every step: 27 graded steps and 1 908 units.** No solver asked a question, and the oracle-error rule was never needed. All three wrote their own semantic-version comparison instead of calling npm `semver`, and all three got prereleases and `1.10.0 > 1.9.0` right. They also handled month boundaries for coupons, a trial that crosses a month, plan changes within a month, annual billing every twelfth month, the minimum invoice on the converted total, and rounding halves up to whole kronor.

**Stage 2 is not run**, as the decision rule says. H4 and H5 are not tested.

### What this means for the goal

Eight trials and 34 solver runs have now produced no substantive error in typed Python written by Claude Haiku. The tasks covered a complete specification, ambiguous changes, a silent library upgrade, cross-cutting changes in inherited code, and eight interacting rules from an empty file. The goal's condition, fewer errors than typed Python, assumes there are errors to reduce. On every task tried so far, there are none, so the condition cannot be met by measurement. It can only be met by a task chosen because Python fails on it, and that would not be a measurement of B.
