# Source adoption: compile restricted Python into native B (v0.7)

**Experimental, implemented and tested.** This is the first foreign-library path where B can examine a Python function's **implementation**, rather than solely trusting a foreign signature. It is not general-purpose Python translation and it does **not** establish that the function performs its intended job.

## Why it exists

The ordinary `use py:module as m` imports and calls Python dynamically. Its declared types are assumptions; the effect is always `foreign`. This works with real packages but does not allow a B `pure` function to safely include unknown foreign behavior.

`adopt py:module.function as local_name` instead **reads the exact Python `.py` file**, parses an allowed single-expression function, converts that expression to B's own syntax tree, and runs **the same B type, function and effect checker used for native B**. The Python code is not imported, called, or copied blindly at runtime; B emits a native B function. The BIR function records the `py-source` origin and SHA-256 digest of the entire source file.

```bee
permit [console]
adopt py:b_examples.pure_kernels.forward as next
fn twice_next(x: Int) -> Int pure = next(x) * 2
print twice_next(20)
```

Use `b check examples/adopt.bee --strict`, `b run examples/adopt.bee`, `b build examples/adopt.bee`, or `b ir examples/adopt.bee` to inspect the generated B function, effect list and provenance.

## Exact accepted subset

The Python function must be top-level, synchronous, undecorated and have only positional arguments, each annotated exactly `int`, `float`, `bool`, or `str`; the return annotation must also be one of these four types. No default values, argument unpacking, keyword-only arguments, generics, implicit `Any`, or inherited methods.

The function body is exactly one `return expression`, preceded optionally by a docstring. The expression may contain finite scalar constants, parameter references, unary `-`/`not`, binary `+ - * / %`, `and`/`or`, a single supported comparison, or an `x if condition else y` expression. Every node is converted to an explicit B expression and type-checked under **B's own** rules. The B checker rejects incorrect return types, parameter-capture attempts, unsupported syntax, calls, subscript access, attributes, comprehensions, and all other dynamic constructs. A Python module with unsupported top-level statements is not itself executed: **only the selected function AST is compiled**.

The compiler rejects unsupported functions with `E_ADOPT`, or existing B diagnostics such as `E_TYPE`. There is no fallback to unchecked dynamic execution.

## Guarantees and their boundaries

**Guaranteed by the implementation design, subject to compiler correctness:** selected functions contain no calls or attribute accesses in the accepted AST. B's native checker identifies no tracked foreign/console effect in them. Typed argument and return guards enforce the declared B type domain. The emitted B program does not execute the original module's top-level code. The BIR provenance digest refers to the source bytes that were read during compilation.

**Not guaranteed:** equivalence to arbitrary Python execution, absence of runtime exceptions, termination, low CPU/memory consumption, behavior of third-party code outside the supported expression subset, correctness relative to human intent, or protection against hostile compiler import hooks. `pure` here means only no *tracked external effects* on B's supported operations. Mathematical properties require separate B contracts and supported proofs.

The source is **translated to B semantics**, not executed as Python: accepted values must pass B's exact boundary guards, B may reject Python's permissive coercions, and Python's module-level monkeypatching is intentionally ignored. `PathFinder` locates normal packages without importing their `__init__.py`. For top-level packages installed through editable-install meta-path finders, the compiler falls back to `importlib.util.find_spec` **only for the top-level name** (never a dotted name); that may invoke trusted custom finder code. This is **not a secure way to inspect untrusted packages**.

The recorded SHA-256 hash is provenance, not an independent signature or vendor certification. B does not check that an external package stays unchanged after compilation; it doesn't need that package at runtime for adopted functions because the accepted body is compiled into B.

## Measuring actual coverage

`b adopt-audit py:MODULE --json` enumerates top-level public Python source functions and tells you which ones can pass B's static source-adoption and type checks. It is intentionally different from `b audit py:MODULE`: the latter measures only supported signatures, not source-adoption eligibility.

**Observed locally, 21 November 2026, CPython 3.13:**

| Library | Adoptable source functions | Public functions directly defined in the module |
| --- | ---: | ---: |
| `b_examples.pure_kernels` (controlled sample) | 5 | 9 |
| `statistics` (standard library) | 0 | 20 |
| `textwrap` (standard library) | 0 | 5 |

Other packages with binary implementations or namespace root modules may have **no Python `.py` source available** for the root target; this is not equivalent to a package coverage score. These are not results about how much *existing library behavior* B can dynamically call. Dynamic interop and source adoption address different cases.

This negative result matters: the initial subset is useful for small, typed, pure kernels, **not** an automatic replacement for full NumPy, pandas, .NET or third-party Python. Reaching those requires intentionally adding semantics, better types, and composition mechanisms, not just guessing unsupported operations.

## Research hypothesis and kill criterion

**Hypothesis:** Reusing a checked expression subtree from an existing library, under B's strict type domain, can reduce newly generated code and external effect assumptions for AI-written B programs while preserving a meaningful, pre-execution validation boundary.

**Kill criterion:** On held-out tasks, if source adoption rarely matches useful functions, changes behavior unexpectedly, or costs more in build complexity than it saves in generated code and review effort, reject or narrow the feature. Compare B `adopt`, ordinary B `use`, and direct native B functions under the same task, runtime and model budget. No such end-to-end AI benchmark has been performed yet.
