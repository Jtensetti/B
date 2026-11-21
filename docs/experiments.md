# B experiments — reproducible evidence

## B v0.3 implemented experiments

1. **Typed foreign Python imports:** real `statistics.median` and `json.dumps` can be used in strict mode after explicit `foreign` declarations without modifying the built-in registry. The checker validates argument types and arity, and runtime guards check returned values. Fake signatures are deliberately tested and can fail at runtime; the declared behavior remains an unproved assumption.
2. **Native B conditionals:** `if condition then a else b` parses into B's AST, performs static branch type checks, propagates statically known results and lowers into a Python conditional expression. Only the selected branch executes at runtime.
3. **Nested dynamic guards:** narrowing `List[Any]` to `List[Int]` now requires a runtime check of every element. A mixed literal and a dynamically imported JSON result are tested as negative cases.
4. **True multi-runtime text processing:** B calls `statistics.mean`, .NET's `Regex.IsMatch` and .NET's `Math.Sqrt` in a single program. The .NET host's actual execution is exercised in GitHub CI; when .NET is unavailable locally, its runtime tests are marked skipped, not passed.
5. **Boundary normalization discovered by CI:** .NET serializes the floating-point value `6.0` as JSON `6`. The initial bridge accepted the result as a `Float` but left a Python `int` in B. B now converts compatible numeric values to finite Python floats, recursively normalizes typed lists, and rejects an integer too large for `Float`. The actual .NET host test exposed this defect.
6. **Machine-readable diagnostics and explicit extension policy:** `b check FILE.bee --json` outputs accepted/rejected status, static diagnostics and foreign assumptions. `.b` and `.bsrc` remain compatible; `.bee` is the preferred source extension.
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
b check examples/auto_discovery.bee --strict --json
b run examples/polyglot.bee
b inspect py:b_examples.demo_lib
b inspect net:System.Math --verify
```

The final test requires .NET 10. CI installs the SDK and builds the host. To test model-directed programming, compare this B implementation with real Python/.NET baselines using the same model, tasks, attempts and compute budget. Include library availability, typing effort and FFI adapter creation in the full cost.


## B v0.3 incremental experiments

8. **Non-executing Python signature extraction:** `b_examples/demo_lib.pyi` is parsed using `ast.parse`, not imported. B uses its supported typed exports with no explicit `foreign` declarations. Tests assert that checking a source with an import-time side effect does not trigger the target module; parent package resolution remains a documented exception.
9. **Reject rather than invent signatures:** unknown typing constructs, overloads and nonrepresentable annotations are skipped. Strict checking then refuses the unknown call. Explicitly wrong argument types and positional argument counts fail before execution.
10. **Foreign contract honesty:** a stub that claims the wrong return type gets caught by a runtime guard, but a correct type with a wrong value would remain undetected. `b check --json` records metadata signatures as assumptions even in strict mode.
11. **.NET metadata drift gate:** a reflection endpoint lists transport-compatible overloads on the *already permitted* .NET types. `b inspect net:System.Math --verify` compares the host results with the manifest used for checking. This is a metadata consistency test, not general .NET reflection or proof.
12. **Source filename transition:** `.bee` is the preferred source form, while `.bsrc` and `.b` are accepted for compatibility. `.be` is intentionally rejected due to the existing Berry language.

These experiments do not yet benchmark any language model, the token budget or correctness against independent real-world tasks. Future benchmarks must account for the cost of acquiring metadata and building adapters rather than comparing only source length.

## B v0.4 experiments: polymorphism and boundaries

13. **Python overloads:** parse a pair of real `@overload` variants from `.pyi` as an `Overloads` value. `Int` and `Text` inputs select distinct runtime signatures; an `Any` input that could match both fails in B before execution (`E_OVERLOAD_AMBIGUOUS`). This is intentionally *not* the full Python overload-matching specification.
14. **Explicit absence:** `Option[T]` is distinct from `T`. A function returning `int | None` or `Optional[int]` produces `Option[Int]` in B; `let value: Int = possible` is rejected at check time.
15. **Typed dictionaries:** `Dict[Text,T]` and `{ "key": value }` literals are first-class B operations. Dictionary values and keys are recursively validated across typed boundaries. An intentionally dishonest stub returning `dict[str,int]` with string values is rejected at runtime.
16. **Earlier rejection:** incompatible concrete types in a literal list or dictionary now fail immediately, rather than turning into an accidental dynamic `Any` and failing after execution.
17. **Bounded trust:** the `.pyi` source is parsed, not imported as executable metadata. This does not validate the *semantic truth* of any stub or the target package's side effects.
18. **Historical extension checks:** `.bee` stays canonical, `.b4` is a supported, optional alias. `.bi` is already taken by FreeBASIC. Extension collision is not a property the compiler can solve.

Repeat B 0.4 experiments:

```sh
pytest -q
b inspect py:b_examples.poly_lib --json
b check examples/polytypes.bee --strict --json
b run examples/polytypes.bee
```

19. **Typed fallback with no duplicated effects:** `optional ?? fallback` requires `Option[T]`, rejects incompatible defaults, evaluates the optional-producing expression once and never evaluates the default unless needed. A stateful foreign function is used as the regression test.

As in earlier versions, these are language and interoperability tests, **not** measurements of independent AI-generated code quality, total cost per correct task, or general proof of imported library behavior.
