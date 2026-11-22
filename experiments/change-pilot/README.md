# Billing change pilot

This single-task pilot tests the mechanics of an AI-assisted maintenance evaluation. An existing billing API priced a run using a strictly positive count. A product change allows the count to be zero. Two clients need special behavior for empty runs, a third should work unchanged, and an unrelated fee calculation must keep working.

## Protocol

Three fresh solver contexts received the same task and starting behavior. Each had a separate working directory, one final submission and up to three invocations of its local checker. The written instructions excluded the oracle, siblings' directories, the network and other agents. The host filesystem was shared; isolation was instructional. The baseline B sources came from commit `6b4b9a0069e824574f86d8bd51080a85cf58451e`. Python 3.12.14, Lark 1.3.1 and mypy 1.20.2 were used locally.

The B checker ran `b check --json` and four public examples. The 0.8 condition also displayed `b impact before.bee billing.bee --json`. Python received annotated source, runtime assertions, `mypy --strict` and the same four examples. No condition required a clean static proof report to pass the behavioral oracle. A successful invocation is evidence only for the examples it ran.

The task and oracle were frozen before the solvers started. Their SHA-256 digests are:

- `TASK.md` — `4f5f5acf2dbec1e0851f5c15ce0b23416933b9a0bee8a578c3b9855fa697a038`
- `score.py` — `c5c253c3d8522e5129dcca34eac95b8e9f9c43055b0405c5a7da375f1c667e06`

The oracle checks 110 function/input pairs against independently calculated values, return types and rejection of negative extra counts. Two pairs also appear in the public smoke test. Both starting implementations satisfy 98/110 oracle cases. Checks within a submission are correlated; the experimental unit is a solver submission.

## Observed results

| Condition | Public cases | Oracle cases | Checker invocations | Functions edited |
| --- | ---: | ---: | ---: | --- |
| B 0.7 | 4/4 | 110/110 | 1 | billable, rate, carry |
| B 0.8 | 4/4 | 110/110 | 3 | billable, rate, carry |
| Typed Python + mypy | 4/4 | 110/110 | 1 | billable, rate, carry |

All three solvers preserved the original label and fee functions. Python passed mypy in strict mode. B 0.7 retained warnings for runtime contract checks. B 0.8 proved the producer's new nonnegative guarantee and the call preconditions, but its proof gate still reported two unresolved denominator obligations in the submitted solution. The callers checked `extra == 0` before dividing. A published bound of `result >= 0` cannot establish that `billable(extra)` is positive specifically when `extra` is positive.

In a separate diagnostic test we made only the producer edit, replacing the first declaration with the one shown below while leaving both clients unchanged.

```bee
fn billable(extra: Int) -> Int pure requires extra >= 0 ensures result >= 0 = if extra == 0 then 0 else extra + 1
```

The four public examples passed. The oracle caught 12 failures, all in `rate` and `carry` on empty runs. B 0.8's impact report independently identified two lost nonzero proofs, one in each of these clients. It also recorded the change to the producer's proved postcondition.

There was one solver per condition and one explicit task with a small API. The outcome shows a ceiling on behavioral accuracy here. Three checker invocations versus one cannot establish a language effect. The pilot had no token or inference-cost telemetry, fixed model-build identifier, repeated trials, equivalent relational verifier for Python, or timed contract-authoring stage. It cannot estimate total cost per correct edit. Task, fixtures, scorer and submitted patches are published for replay; future blinded evaluations require fresh tasks.

## A follow-up repair

After scoring the three submissions, we wrote `guarded-count.bee` as a separate experiment. Two small helpers test the actual denominator before division or remainder. This version passes all 110 cases and both proof checks. It shows that the existing verifier can express one correct repair. Whether teaching the model that pattern is cheaper than extending the contract language is an open question.

```sh
b check guarded-count.bee --strict --require-proofs
python score.py guarded-count.bee
```

## Replay

With the chosen B revision and dependencies installed, run from this directory:

```sh
work=$(mktemp -d)
cp billing.bee "$work/"
patch -d "$work" -p1 < submissions/b-0.7.patch
python score.py --public "$work/billing.bee"
python score.py "$work/billing.bee"
```

For B 0.8 select `submissions/b-0.8.patch`. For the Python condition, copy `billing.py`, apply `submissions/python.patch`, and run `mypy --strict` and the scorer on the patched Python file. Run each B condition with its original compiler revision.
