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

## Trial 4: changes only, from inherited code

The release trial showed B losing on changes. This follow-up measures changes alone. Four new Haiku solvers each started from a working program written by a solver in the trial above: [`b2.bee`](solutions/b2.bee) for B and [`py1.py`](solutions/py1.py) for Python. Both pass all 15 fixtures. They received four changes in turn ([steps 6–9](steps/)). The changes interact: the stable-only weekly count, ignoring future-dated releases in all five outputs, stale thresholds per package, and days since the latest release. Three new fixtures cover them, for 15 in total. Solvers were told what the program does, but not how it is written.

| Solver | Change 1 | Change 2 | Change 3 | Change 4 | Total output tokens | Tool calls | Hidden tests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| B 1 | 7,439 | 5,389 | 3,444 | 2,334 | 18,606 | 12 | 60/60 |
| B 2 | 6,937 | 11,940 | 10,399 | 3,088 | 32,364 | 22 | 60/60 |
| Python 1 | 4,142 | 4,146 | 6,096 | 4,666 | 19,050 | 15 | 60/60 |
| Python 2 | 3,626 | 3,750 | 6,046 | 4,622 | 18,044 | 17 | 60/60 |

Data: [grades](results/changes/grades.txt) and [work](results/changes/work.json). Wall times are omitted, because the runtime's timestamps for resumed agents are unreliable.

- **No errors again.** All four passed every fixture after every change. No change broke an earlier requirement, in either language.
- **B's cost after learning varies with the solver, not the language.** Change 1 includes reading the B guide. After it, B 1 spent 11,200 output tokens on three changes, against 14,400–14,900 for Python. B 2 spent 25,400. Taken together, B cost about 1.37 times Python's output tokens, down from 1.65–2.5 in the earlier trials.
- **What the B solvers did with the new features:** both filtered future releases with one comprehension and reused it, exactly as the Python solvers did. One B solver still wrote a dummy `{"": 0}` fallback, although `x ?? {}` now works. The guide's one line about it was not enough.

## Summary of four trials

| Trial | Errors, B vs Python | Total output tokens, B ÷ Python |
| --- | --- | ---: |
| Journey (Sonnet, npm semantics) | 0 vs 0 | 0.55 |
| Shipping (Haiku, Python library) | 0 vs 0 | 3.6 |
| Releases (Haiku, mixed, with the guide) | 0 vs 0 | 1.4 |
| Changes only (Haiku, inherited code) | 0 vs 0 | 1.37 (B 1 alone: 1.00) |

Sixteen solver runs and 25 graded steps or changes per language have produced no wrong output in either language. The long-term goal asks for fewer errors, and these tasks cannot show that. Self-tested, clearly specified tasks are too easy for today's models in both languages. Less total work holds where B borrows a library that the other language lacks. With today's B it does not hold in general. The next measurement has to put the solvers where errors actually occur: changes whose effects reach code the solver does not read, specifications that leave a case open, and libraries that change underneath the program. B's checks (`example`, `keeping`, units at the border, library examples) are built for exactly these, and none of the four tasks needed them.
