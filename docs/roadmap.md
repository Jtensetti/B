# Roadmap and implementation ledger

## v0.1 — implemented

- [x] Independently parsed `.b` program syntax and AST
- [x] Immutable top-level bindings and typed expression functions
- [x] Static type checks with concise named diagnostics
- [x] Constant folding for checks and division-by-zero rejection
- [x] Python AST lowering and a `b` CLI (`check`, `run`, `build`)
- [x] Real imports from installed Python libraries
- [x] Typed manifest for a small number of Python and .NET symbols
- [x] .NET 10 host source with JSON-lines bridge to `System.Math` subset
- [x] Python unit tests, cross-runtime integration test and GitHub Actions workflow

**Testing caveat:** local environment has Python but no .NET SDK; true cross-runtime execution must be validated by GitHub Actions or a machine with .NET 10 installed. Do not mark this as validated until successful CI evidence exists.

## v0.2 — correct the foundations

- [ ] More complete type soundness tests and typed AST property tests
- [ ] Explicit coercion rules, numeric limits, rounding and error semantics
- [ ] Proper B program modules and import resolution
- [ ] Data records, `Option`, `Result`, branches and loops
- [ ] Source locations and structured error responses for AI tools
- [ ] Metadata provenance/version locking and signature file format
- [ ] Cross-runtime exception mapping and process lifetime specification
- [ ] Sandboxed Python worker or capability-based isolation for untrusted programs

## v0.3 — broad interoperability

- [ ] Generate Python bindings from type stubs/inspectable metadata
- [ ] Generate .NET bindings from metadata and overload resolution
- [ ] Typed bulk arrays and zero-copy shared memory where verified safe
- [ ] Add Rust via C ABI / WIT component boundary
- [ ] Record runtime effects, failures and allocation ownership

## v0.4 — real verification

- [ ] Formal operational semantics for stable core IR
- [ ] Machine-checkable contracts and pure-effect separation
- [ ] Incremental verification with dependency graph
- [ ] Distinguish `proved`, `disproved` and `unknown` at each contract
- [ ] Differential and mutation testing against native languages

## v0.5 — optimize for models, based on measurement

- [ ] Compact model-facing serialization derived from IR
- [ ] Controlled grammar/type guided token generation
- [ ] Versioned change operations instead of whole-file rewrites
- [ ] Real cost/accuracy benchmarks against competitive baselines
- [ ] Custom tokenization or finetuning only if the measured gain justifies it

## Rejected premature design commitments

- A universal replacement for Python/C#/Rust without adapters.
- Automatic proof of arbitrary third-party libraries.
- Assuming natural-language-like ambiguity improves program generation.
- Equating shorter source with lower actual model cost.
