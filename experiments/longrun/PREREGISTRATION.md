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
