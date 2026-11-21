# B roadmap — evidence before promises

B is an independent language with a parser, type checker and Python-AST lowering, plus explicit foreign adapters. The target is fewer model-generated decisions and greater verified capability per token/cost, while reusing existing ecosystems. No AI programming benchmark has yet confirmed this advantage.

## Implemented through B 0.6

- [x] B syntax, AST, expression-bodied functions, immutable bindings, operators, lists, conditionals.
- [x] `Option[T]` and `Dict[Text,T]` with literals/inference and recursive runtime type guards.
- [x] Typed lazy `??` fallback; its left operand executes once even when it is a foreign call.
- [x] Reject known heterogeneous collection values before running (rather than delaying to dynamic checks).
- [x] Conservative Python `.pyi`/`.py` AST signature extraction, trailing defaults and two-or-more `@overload` declarations.
- [x] Reject ambiguous overload resolution instead of guessing a result type.
- [x] Real Python imports and explicitly permitted .NET Math/Regex methods.
- [x] Runtime boundary value guards, metadata provenance, JSON diagnostics, strict-mode preflight checks.
- [x] B polyglot and negative tests, Python 3.11/3.13 + .NET 10 GitHub CI.
- [x] `.bee` canonical, `.b4` optional, `.bsrc`/`.b` backward compatible.

## Next: coverage with honest static information

- [ ] `Result[Ok, Error]`, records and stable object/resource reference semantics.
- [ ] Keyword arguments, Python typing overload rules and more of typeshed (`Sequence`, `Iterable`, `Literal`, `Protocol`, selected generics).
- [ ] .NET generic signatures and permission-scoped metadata adapters for selected real packages.
- [ ] Versions/lockfiles and explicit dependency/version provenance for metadata; cache signatures by version.
- [x] Typed BIR v2 as common semantic representation, consumed by Python backend; JSON inspection and conservative native constant optimization.
- [ ] Additional lowering backends, stable IDs and independently verified BIR loading.
- [x] Build a reproducible, narrowly defined direct-signature coverage audit, report negative results on NumPy/pandas/SciPy.
- [ ] Improve real-world library coverage and measure more of the *public API*, including re-exports, classes and methods.

## Later: guarantees and machine efficiency

- [x] Conservative `pure` and `permit` effect classification for native and foreign operations; imports remain broad and untrusted.
- [ ] **Fine-grained**, enforceable effect capabilities and bounded resource use for imported operations.
- [x] `requires`/`ensures` with runtime enforcement and soundly bounded Int interval proofs.
- [ ] General specified invariants with a separately checkable proof/verification kernel.
- [ ] Incremental checking and compilation of versioned program IR nodes; local edits that preserve unaffected code.
- [ ] Other runtimes through real adapters (Rust/C ABI, JVM, WASM Component Model/WIT).
- [ ] Controlled AI benchmark: B vs Python/C#/Rust with matched model, library access, tokens, runtime, retries and correctness tests.
- [ ] Constrained decoding and compact machine-facing representation only after measuring performance.

## Things B does *not* establish

- Any imported library is functionally correct merely because it has a type stub.
- All Python annotations, overloads, and .NET assemblies are understood by B.
- Strict checks guarantee the user's intended behavior or side-effect safety.
- Fewer source characters automatically mean fewer model tokens or lower total cost.

## Research after BIR

See [research directions](research-directions.md) for falsifiable proposals spanning effect systems, machine-checkable contracts, dimensional types and incremental compilation. These are hypotheses, **not implemented language features**.

B 0.6 tracks a **limited effect inventory** rather than installing a real OS-level capability system. See [contracts and effects](contracts-effects.md).
