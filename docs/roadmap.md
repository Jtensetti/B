# B roadmap and implementation ledger

The long-term target is a new language with its own semantics, a minimal model-friendly representation, strong preflight checking and reliable access to existing ecosystems. Features below are intentionally distinguished by execution evidence, not by aspiration.

## v0.1 — completed foundation

- [x] B's own parser and syntax tree
- [x] Native immutable bindings, typed expression functions, lists and arithmetic
- [x] Initial type rules and compile-time constant checks
- [x] Python AST backend and `b check/run/build`
- [x] Python imports and a limited .NET Math bridge over JSON lines
- [x] Local unit tests and cross-runtime CI

## v0.2 — implemented and undergoing integration checks

- [x] New recommended extension `.bsrc`, retaining `.b` compatibility
- [x] B conditional expressions with static branch checks
- [x] `foreign` to type real imported Python methods without changing the compiler registry
- [x] Runtime checks on known foreign argument and result boundaries
- [x] Recursive dynamic-list guard when narrowing `List[Any]`
- [x] Additional .NET `Regex.IsMatch` bridge and cross-runtime integration test
- [x] Machine-readable `b check --json` results including trusted foreign assumptions
- [x] Deterministic differential testing of 300 generated expressions
- [x] Basic `.bsrc` VS Code grammar

## v0.3 — scale the interoperability

- [ ] Automatically derive and cache Python signatures from trusted stubs (`.pyi`) with provenance and version locks
- [ ] Generate .NET bindings from metadata with overload, nullability and exception handling
- [ ] Structured records/tuples, nullable types and explicit failure values (`Option` / `Result`)
- [ ] Foreign handles for objects, explicit resource lifetime and useful bulk array formats
- [ ] Check both supported and unsupported behavior in version-pinned cross-runtime tests
- [ ] Define a stable typed intermediate representation independent of Python AST

## v0.4 — executable guarantees

- [ ] Formal semantics for the B core and a small independently checkable invariant language
- [ ] Explicit effect declarations and capabilities for foreign modules
- [ ] Incremental compilation and proof caching over unchanged IR nodes
- [ ] Trusted backend and compiler validation / differential testing
- [ ] Safer isolation for untrusted programs; runtime guards alone are not isolation

## v0.5 — model optimization

- [ ] Stable machine-facing grammar/serialization derived from B IR
- [ ] Constrained decoding against allowed operations and types
- [ ] Versioned localized transformations to prevent regressions
- [ ] Compare B vs existing languages using the same AI model and full cost budget
- [ ] Distinguish model token improvements from correctness and library coverage

## Excluded assumptions

- “A new spelling or shorter syntax is automatically cheaper for an LLM.”
- “A declared foreign function signature proves the function behaves correctly.”
- “The Python backend currently produces native B executables.”
- “An empty warning list means that every observable behavior is correct.”
