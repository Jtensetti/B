# B

**B is an experimental, independently parsed and type-checked programming language for composing existing ecosystems.** Its primary goal is to reduce unnecessary implementation work without pretending that an imported library is automatically correct.

**Version 0.5 (research prototype).** Preferred source suffix: `.bee`; `.b4`, `.bsrc` and `.b` are supported aliases. B is unrelated to the historical Bell Labs B language.

> **Safety and maturity:** B is not a sandbox, a general-purpose native compiler, a proof assistant or a complete Python/.NET type checker. `b check --strict` only accepts programs without *known static warnings in the supported subset*. Import signatures are assumptions, not proofs. Executing B can run arbitrary installed Python code.

## What is new in B 0.5?

A real, **typed backend-neutral intermediate representation (BIR)** sits between B source and the executable backend:

```text
  .bee source
      |
  B parser + B checker + type/provenance catalog
      |
  BIR v1: types, operations, foreign interfaces and obligations
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
| B language | Own grammar, immutable names, typed functions, conditions, collections, `??` | Loops, records, pattern matching, user generics |
| BIR v1 | Typed semantic nodes, foreign catalog, JSON view, pure constant optimization | Stable serialized execution, source maps, multi-target lowering |
| Python libraries | Actual import/call, limited annotation discovery, overloads and dynamic fallback | Full typeshed, re-export tracking, package-version locking |
| .NET libraries | Restricted `System.Math` and `Regex` host, metadata verified in CI | Arbitrary assemblies, object models, reflection-based adapters |
| Correctness | Static syntax/types/known constant errors; runtime boundary guards | Formal correctness proofs, effect guarantees, trusted execution |
| AI advantage | Explicit machine-readable IR and diagnostics | Any measured improvement in AI's correctness or tokens |

## Project references

- [Language and grammar](docs/language.md)
- [BIR semantics and implementation](docs/bir.md)
- [Cross-language library bridges](docs/interop.md)
- [Real-library audit](docs/library-audit.md)
- [Experimental evidence](docs/experiments.md)
- [Architectural decisions](docs/architecture.md)
- [Research directions beyond interoperability](docs/research-directions.md)
- [Roadmap](docs/roadmap.md)

**Status:** the code is a research prototype, with tests on the implemented subset. An independent AI building and modifying a substantial B application has **not** yet been evaluated.

MIT licensed.
