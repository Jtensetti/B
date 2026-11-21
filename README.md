# B

**B is an experimental, independently parsed and type-checked programming language for composing existing ecosystems.** Its primary goal is to reduce unnecessary implementation work without pretending that an imported library is automatically correct.

**Version 0.9 (research prototype).** Preferred source suffix: `.bee`; `.b4`, `.bsrc` and `.b` are supported aliases. B is unrelated to the historical Bell Labs B language.

> **Safety and maturity:** B is not a sandbox, a general-purpose native compiler, a proof assistant or a complete Python/.NET type checker. `b check --strict` only accepts programs without *known static warnings in the supported subset*. Import signatures are assumptions, not proofs. Executing B can run arbitrary installed Python code.

## When a result depends on the input

In B 0.9 a producer can publish a checked rule such as “after tick three, velocity is negative.” A caller in that time range can prove that descent speed is positive. A second caller can safely use it as a divisor. A variant in which the body rebounds at tick five loses all three proofs.

```sh
b check examples/mechanics/flight.bee --strict --require-proofs
b impact examples/mechanics/flight.bee examples/mechanics/rebound.bee
```

On a sequencer maintenance task, six AI submissions passed all 102 behavior checks. The initial difference in checker calls disappeared when a new group learned its configuration upfront. See [conditional guarantees, examples and limits](docs/conditional-guarantees.md), the [AI maintenance experiment](experiments/law-pilot/README.md) and the [cross-language operator probe](experiments/operator-correspondence/README.md).

## What happens when a contract changes?

A provider used to promise a positive count. Its new contract permits zero. B 0.8 can follow that change into two callers. Adding a reserve of ten still produces at least ten. Dividing a cost by the count loses its guarantee that the denominator is nonzero.

```sh
b impact examples/revisions/count-positive.bee examples/revisions/count-zero.bee
b check examples/revisions/count-positive.bee --strict --require-proofs --json
b check examples/revisions/count-zero.bee --require-proofs --json  # exits 1
```

The report identifies the function, expression site, requirement, proof status and direct dependencies. Native B functions can use independently established integer contracts across calls. The analysis distinguishes a lost guarantee from a demonstrated runtime failure. See [contract analysis and revision comparison](docs/composition.md).

In a [single-task AI maintenance pilot](experiments/change-pilot/README.md), B 0.7, B 0.8 and typed Python each passed the same 110 behavior checks. A separate partial edit passed all four public examples while breaking two callers. B 0.8 identified both lost proofs. Total token and inference costs were unmeasured.

## Checked Python source adoption (0.7)

B can now compile a **small, explicitly restricted subset of Python source into native B functions**, rather than importing an entire Python module at runtime:

```bee
permit [console]
adopt py:b_examples.pure_kernels.square as sq
fn triple_square(x: Float) -> Float pure = sq(x) * 3.0
print triple_square(4.0)
```

The `adopt` directive reads a top-level Python function, translates allowed expression-only code into BIR, type-checks and emits a native B function. **The original Python module is not imported or executed** by that compiled function. Unsupported Python code is rejected (`E_ADOPT`), not silently interpreted. BIR records the source file SHA-256. Inspect candidates with `b adopt-audit py:MODULE --json`.

**Measured limitation:** the first narrow experiment adopted 5/9 functions in our controlled example but **0/20** in Python's real `statistics` module and **0/5** in `textwrap`. This is *not* general library integration or mathematical verification. See [the scope, results and limitations](docs/source-adoption.md).

## Contracts and effects (introduced in B 0.6)

**Effect budgets and function contracts are native B syntax**, checked before the Python backend executes. B can now prove a narrow family of integer postconditions, reject certain broken preconditions and effects, and enforce other contracts at runtime:

```bee
permit [console]
fn successor(x: Int) -> Int pure requires x >= 0 ensures result > 0 = x + 1
print successor(41)
```

`pure` forbids unknown foreign effects inside a B function. `permit [...]` tracks a small set of program effects (`console` and `foreign`), **not actual OS capabilities**. BIR records whether a postcondition is proved using integer intervals or only checked at runtime. An imported function's type does not prove its behavior. See [the contract and effect specification](docs/contracts-effects.md).

## BIR pipeline

A real, **typed backend-neutral intermediate representation (BIR)** sits between B source and the executable backend:

```text
  .bee source
      |
  B parser + B checker + type/provenance catalog
      |
  BIR v2: types, contracts, effect classifications, source provenance
      |
  conservative pure-operation optimization
      |
  Python AST backend --> CPython / real Python packages
                        --> explicit typed .NET bridge
```

The Python backend **consumes BIR**, not the source language's syntax tree. BIR is JSON-inspectable; it can preserve a referenced Python or .NET function's assumed signature, backend and provenance. This makes another backend possible in principle, but **only the Python lowering backend is implemented**.

BIR optimization folds supported pure literals without evaluating foreign functions or removing runtime type guards.

## A B program

```text
use py:statistics as stats
use net:System.Math as Math

fn square(x: Float) -> Float = x * x
let values = [3.0, 4.0, 5.0]
let avg: Float = stats.mean(values)
let result: Float = Math.Sqrt(square(avg) + 9.0)
print result
```

This is B source, not a Python program. The `statistics.mean` function runs in CPython and `System.Math.Sqrt` through the explicit .NET host. Both calls appear in the **same** BIR vocabulary with distinct foreign backend tags.

## Install and run

Requires Python 3.11+. Running the .NET example also requires the .NET 10 SDK.

```sh
python -m pip install -e '.[dev]'
b check examples/adopt.bee --strict
b run examples/adopt.bee
b adopt-audit py:statistics --json
b check examples/contracts.bee --strict --json
b run examples/contracts.bee
b check examples/effects.bee --strict
b run examples/effects.bee
b check examples/polyglot.bee --strict
b run examples/polyglot.bee
b ir examples/polyglot.bee --strict           # checked BIR as JSON
b ir examples/polyglot.bee --optimized        # BIR after pure literal folding
b build examples/polyglot.bee                 # show emitted Python backend code
b inspect py:b_examples.poly_lib --json      # static signatures
b audit py:b_examples.demo_lib --json        # coverage: direct functions only
pytest -q
```

To measure coverage of installed real packages (no installation is performed):

```sh
python -m scripts.audit_libraries > audit.json
b audit py:numpy --json
b run examples/numpy_unchecked.bee  # requires NumPy; dynamic, not strict-safe
```

## The important negative result

Our local audit on **21 November 2026** found that B 0.5 could statically understand **0 of 1 directly declared functions** in NumPy's root stub, which also contains hundreds of named re-exports. In the submodule `numpy._core.fromnumeric`, B could parse **0 of 41** direct public function declarations. This **does not mean NumPy has one function, or that zero NumPy functions can be executed by B**: it means our intentionally restricted signature reader cannot yet interpret its complex API definitions. See [the measured audit](docs/library-audit.md), [raw observation](docs/coverage-observed-2026-11-21.json) and [coverage tool](b_lang/audit.py).

This limitation matters more than adding new punctuation or another file extension. Next steps must tackle public re-exports, object/array types, generics, keyword arguments and verified conversions.

## Implemented boundaries

| Layer | Working today | Not yet provided |
| --- | --- | --- |
| B language | Own grammar, immutable names, typed functions, conditions, collections, `??`, `pure`, `requires`, `ensures`, `permit`, `adopt` | Loops, records, pattern matching, user generics |
| BIR v2 | Typed semantic nodes, function contracts, effect inventory, foreign catalog, JSON view, pure constant optimization | Independently verified IR loading, source maps, multi-target lowering |
| Python libraries | Actual import/call, limited annotation discovery, overloads, dynamic fallback and narrow source adoption | Full typeshed, re-export tracking, package-version locking |
| .NET libraries | Restricted `System.Math` and `Regex` host, metadata verified in CI | Arbitrary assemblies, object models, reflection-based adapters |
| Correctness | Static types/errors, local and cross-function integer interval proofs, revision comparison, runtime contracts and conservative effect classification | General proof system, fine-grained external effects, sandboxing |
| AI advantage | Explicit machine-readable IR and diagnostics | Any measured improvement in AI's correctness or tokens |

## Project references

- [Contract analysis and revision comparison (0.8)](docs/composition.md)
- [Language and grammar](docs/language.md)
- [Source adoption (0.7): rules, measured limits and BIR provenance](docs/source-adoption.md)
- [Contracts, interval proofs and effects (0.6)](docs/contracts-effects.md)
- [BIR semantics and implementation](docs/bir.md)
- [Cross-language library bridges](docs/interop.md)
- [Real-library audit](docs/library-audit.md)
- [Experimental evidence](docs/experiments.md)
- [Architectural decisions](docs/architecture.md)
- [Research directions beyond interoperability](docs/research-directions.md)
- [Roadmap](docs/roadmap.md)

**Status:** the code is a research prototype, with tests on the implemented subset. An independent AI building and modifying a substantial B application has **not** yet been evaluated.

MIT licensed.
