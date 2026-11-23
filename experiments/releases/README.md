# The release trial: mixed vocabulary, with the guide for models

The third trial was chosen before anything was measured, to mix both strengths. Semver ordering and ranges belong to npm. Calendar arithmetic (ISO weeks, day counts) belongs to Python. The solvers were four Haiku instances, two per language. The B solvers were pointed first at [B for models](../../docs/for-models.md), the one-page guide written after the shipping trial.

- **Task** ([steps](steps/)): latest stable release per package, releases per ISO week, stale packages, highest release in a watched npm range, and distinct major versions.
- **Hidden tests:** 12 fixtures, including ISO years 2015-W53 and 2026-W53, leap days, prerelease ordering such as `beta.10` against `beta.2`, build metadata and ranges with `||`. The [oracle](oracle.mjs) uses npm semver, and its ISO weeks were checked against Python's `isocalendar` for 18,250 consecutive days.

## Results

**Correctness.** All four solvers passed all 12 fixtures at all five steps ([grades](results/grades.txt)). For the third time, there were no errors in either language.

**Work.** The model usage limit interrupted three solvers during step 1 for several hours, so wall time is not comparable. Output tokens are:

| Solver | Build | 4 changes | Total | Tool calls | Program |
| --- | ---: | ---: | ---: | ---: | ---: |
| B 1 | 9,906 | 44,423 | 54,329 | 30 | 68 lines |
| B 2 | 8,088 | 53,746 | 61,834 | 28 | 73 lines |
| Python 1 | 12,110 | 26,526 | 38,636 | 20 | 142 lines plus a node subprocess |
| Python 2 | 11,297 | 32,851 | 44,148 | 20 | 142 lines plus a 30-line JavaScript helper |

- **The guide worked for the build.** The B builds cost 8,000–10,000 output tokens, against 40,000–47,000 in the shipping trial, and slightly less than Python's this time.
- **B still lost the changes**, at about 1.65 times Python's tokens. Most of the difference is ISO weeks. Neither B solver could call Python's `date.isocalendar()` with types, because B cannot type a method on a foreign object. Both reimplemented ISO week arithmetic in B and checked it against Python with a few hundred dates.
- **Python went polyglot by hand.** For the npm range step, both Python solvers called `node` through a subprocess. One wrote a JavaScript helper file. That is the sibling idea done manually, with untyped JSON across the border. It worked.
- **Friction reported by the B solvers:** an empty `{}` used as a `??` fallback gives an untyped-value warning, so both wrote a dummy `{"": ""}`.

## The three trials together

| Trial | Model | Errors, B vs Python | Total output tokens, B ÷ Python | Build | Changes |
| --- | --- | --- | ---: | ---: | ---: |
| [Journey](../journey/README.md): npm semantics | Sonnet | 0 vs 0 | 0.55 | 0.15 | 1.8 |
| [Shipping](../shipping/README.md): Python library | Haiku | 0 vs 0 | 3.6 | 7.6 | 2.5 |
| Releases: mixed, with the guide | Haiku | 0 vs 0 | 1.4 | 0.77 | 1.65 |

The long-term goal requires fewer errors and less total work. Neither has been shown. In all twelve solver runs every hidden test passed, so the error criterion never separated the languages. The build got cheaper in B once a guide existed, and when B borrows a library that the other language lacks. Changes cost B 1.65–2.5 times as much in all three trials. Changes are what the goal is about, and they are where B must improve.

## What the changes need

1. **Typed methods on foreign objects**, so that `date.fromisoformat(d).isocalendar()` is a typed call rather than arithmetic rewritten in B.
2. **Empty literals that take their type from context**, so that `x ?? {}` needs no dummy value.
3. Then a trial that measures changes only: start every solver from the same working program, in both languages, and give each the same five changes.
