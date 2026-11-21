# B experiments — reproducible evidence

## B v0.2 implemented experiments

1. **Typed foreign Python imports:** real `statistics.median` and `json.dumps` can be used in strict mode after explicit `foreign` declarations without modifying the built-in registry. The checker validates argument types and arity, and runtime guards check returned values. Fake signatures are deliberately tested and can fail at runtime; the declared behavior remains an unproved assumption.
2. **Native B conditionals:** `if condition then a else b` parses into B's AST, performs static branch type checks, propagates statically known results and lowers into a Python conditional expression. Only the selected branch executes at runtime.
3. **Nested dynamic guards:** narrowing `List[Any]` to `List[Int]` now requires a runtime check of every element. A mixed literal and a dynamically imported JSON result are tested as negative cases.
4. **True multi-runtime text processing:** B calls `statistics.mean`, .NET's `Regex.IsMatch` and .NET's `Math.Sqrt` in a single program. The .NET host's actual execution is exercised in GitHub CI; when .NET is unavailable locally, its runtime tests are marked skipped, not passed.
5. **Boundary normalization discovered by CI:** .NET serializes the floating-point value `6.0` as JSON `6`. The initial bridge accepted the result as a `Float` but left a Python `int` in B. B now converts compatible numeric values to finite Python floats, recursively normalizes typed lists, and rejects an integer too large for `Float`. The actual .NET host test exposed this defect.
6. **Machine-readable diagnostics and explicit extension policy:** `b check FILE.bsrc --json` outputs accepted/rejected status, static diagnostics and foreign assumptions. `.b` remains compatible; `.bsrc` is the preferred source extension.
7. **Differential expression testing:** a reproducible seeded test generates 300 B arithmetic/conditional expressions and compares their results against equivalent Python expressions. This covers only the implemented expression subset, not general correctness.

## What these tests do not establish

- No AI language model has yet generated B programs for an independent benchmark.
- No controlled comparison with Python, C# or other languages for model cost, token count, correctness rate or latency has yet been performed.
- Foreign declarations are assumed, not proven. The imported libraries can perform side effects and can have behavioral bugs.
- The compiler has not been formally verified. Native compiler lowering to Python is not equivalent to an ahead-of-time B executable.
- The current .NET JSON-lines bridge copies data and is not appropriate for high-throughput large-array exchange.

## Repeat

```sh
python -m pip install -e '.[dev]'
pytest -q
b check examples/typed_foreign.bsrc --strict --json
b run examples/polyglot.bsrc
```

The final test requires .NET 10. CI installs the SDK and builds the host. To test model-directed programming, compare this B implementation with real Python/.NET baselines using the same model, tasks, attempts and compute budget. Include library availability, typing effort and FFI adapter creation in the full cost.
