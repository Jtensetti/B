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

**Testing evidence:** local Python run: 27 tests passed, one .NET-dependent test skipped. GitHub Actions completed the Python 3.11 and 3.13 matrix, built the .NET 10 adapter, and ran the real Python/.NET interoperability test successfully in [CI run 44922651119](https://github.com/Jtensetti/B/actions/runs/44922651119). Future changes must keep CI green. Neither unit tests nor CI prove general behavioral correctness.

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
