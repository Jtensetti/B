# Library coverage study — observed 2026-11-21

## Definition

`b audit py:module.name --json` reports how many **directly declared, public top-level function names in one source or `.pyi` stub** B can turn into usable typed signatures. This is a deliberately narrow metric. It is not the percentage of a package's public API or the percentage of code B can run. It excludes re-exported names, functions introduced dynamically, class methods, binary extensions and nested submodules. An API without directly declared `def` statements has an **undefined** direct-coverage fraction, not 100%.

For each target it reports named re-exports, star re-exports, classes, skipped annotations and metadata origin. Python's `find_spec` can execute package parent initializers, so it is **not a hostile-code security boundary**.

## Local observation

Environment: Python 3.13.5; installed distribution versions are shown per row. This is a *local snapshot*, not a comparative benchmark against other languages.

| Module | Distribution version | Direct B-readable functions | Direct public functions | Public named re-exports* |
| --- | --- | ---: | ---: | ---: |
| `b_examples.demo_lib` | local fixture | 3 | 3 | 0 |
| `numpy` | 2.3.5 | 0 | 1 | 368 |
| `numpy._core.fromnumeric` | 2.3.5 | 0 | 41 | 25 |
| `numpy.ma.core` | 2.3.5 | 0 | 73 | 32 |
| `pandas` | 2.2.3 | 0 | 0 | 115 |
| `pandas.core.dtypes.common` | 2.2.3 | 0 | 36 | 38 |
| `scipy` | 1.17.0 | 0 | 0 | 1 |
| `scipy.stats` | 1.17.0 | 0 | 0 | 48 |
| `sympy.utilities.iterables` | 1.14.0 | 0 | 58 | 18 |
| `pydantic._internal._utils` | 2.13.5 | 4 | 12 | 29 |

*The re-export column counts non-private `from ... import ...` names in the inspected file; it is not the total externally accessible symbol count.*

**Interpretation:** B can import and run `numpy.sum([1,2,3])` in **dynamic/non-strict** mode, but cannot yet statically check the signature through NumPy's public root `.pyi`. The largest gap is not the number of files: it is the expressive power of B's boundary types and the ability to follow Python's typing and re-export semantics. B's existing fallback permits functionality but not the intended pre-execution guarantees.

## Reproduce

```sh
python -m pip install -e '.[dev]'
python -m scripts.audit_libraries > audit.json
b audit py:numpy --json
b run examples/numpy_unchecked.bee
b check examples/numpy_unchecked.bee --strict  # expected to reject
```

For third-party targets install those packages separately. The audited source and its version may change. The **raw observation** is in [`coverage-observed-2026-11-21.json`](coverage-observed-2026-11-21.json).

## Highest-leverage next tests

1. Add a safe resolver for Python re-exports that can distinguish actual callable runtime members from type aliases and classes. Measure real coverage gained.
2. Expand B's type vocabulary with structured arrays, result/record/object references and selected generic families **without silently treating unknown types as `Any`**.
3. Add keyword arguments and supported overload semantics with test cases from numpy/pandas stubs.
4. Pin library-version provenance and verify adapter/stub compatibility in CI. Use reproducible benchmark tasks, not percentage alone.
5. Test B against a benchmark of independently specified user tasks. A higher metadata percentage does not, by itself, make AI-generated B applications more correct.
