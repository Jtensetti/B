# B roadmap — evidence before promises

B is an independent language with a parser, type checker and Python-AST lowering, plus explicit foreign adapters. The target is fewer model-generated decisions and greater verified capability per token/cost, while reusing existing ecosystems. No AI programming benchmark has yet confirmed this advantage.

## Implemented through B 0.4

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
- [ ] Typed intermediate representation (IR) shared by multiple backends, not merely Python AST.
- [ ] Measure actual library coverage on pinned NumPy/pandas and .NET packages, including unsupported signatures.

## Later: guarantees and machine efficiency

- [ ] Explicit effect/capability semantics and bounded resource use for imported operations.
- [ ] Specified invariants with a separately checkable proof/verification kernel for a useful subset.
- [ ] Incremental checking and compilation of versioned program IR nodes; local edits that preserve unaffected code.
- [ ] Other runtimes through real adapters (Rust/C ABI, JVM, WASM Component Model/WIT).
- [ ] Controlled AI benchmark: B vs Python/C#/Rust with matched model, library access, tokens, runtime, retries and correctness tests.
- [ ] Constrained decoding and compact machine-facing representation only after measuring performance.

## Things B does *not* establish

- Any imported library is functionally correct merely because it has a type stub.
- All Python annotations, overloads, and .NET assemblies are understood by B.
- Strict checks guarantee the user's intended behavior or side-effect safety.
- Fewer source characters automatically mean fewer model tokens or lower total cost.
