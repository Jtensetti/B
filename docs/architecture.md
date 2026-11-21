# B architecture

## Target

A new programming language with defined semantics and a compiler/runtime that reuses foreign ecosystems through typed adapters. The future machine-facing representation should optimize **total cost per independently correct result**, not merely source length.

## Implemented pipeline (v0.5)

```text
.bee -> B grammar -> B syntax AST -> B checker and foreign catalog
                                    | warnings / trusted assumptions
                                    v
                        BIR v1 (backend-neutral, typed)
                                    |
                         pure BIR simplification
                                    |
                           Python AST backend
                             /             \
                          CPython        JSON-lines .NET host
                         packages       Math/Regex allowlist
```

The lowering backend **consumes checked BIR**, not the parsed syntax. The foreign symbol catalog uses one shape for Python and .NET function signatures, includes provenance and never claims behavior is proved. See [BIR](bir.md) and [library coverage](library-audit.md).

The JSON BIR view (`b ir`) cannot be supplied directly as trusted executable input: it is not independently verified on re-import.

## Proposed design beyond v0.3

1. **Canonical typed B IR (partially implemented):** BIR v1 is a typed semantic tree with a JSON inspection view and one lowering backend; stable IDs, executable deserialization and additional backends are not implemented.
2. **Verified B core:** independent, small proof checker and explicit behavior contracts; track exactly which statements are proved, disproved and unknown.
3. **Generated interfaces:** Python `.pyi`, .NET assembly metadata, C ABI, Rust bindings and Wasm component/WIT produce version-pinned signatures with provenance and conversion rules.
4. **Runtime bridges:** keep native data inside its home runtime; share array/handle data only when lifetime and ownership are controlled.
5. **Model-facing API:** compact serialization for the *same* IR, grammar/type-constrained generation and structured corrections. Measure its value against strong native-language baselines before optimizing a tokenizer.

## Trusted computing base

B's parser, checker, lowering, runtime guard and FFI adapters are all trusted implementation components. Any defect in them can invalidate a check. No third-party library becomes verified merely by being imported. Differential testing and later a small proof checker can reduce—but not magically eliminate—these assumptions.

## Relevant systems to evaluate

MLIR and LLVM intermediate representations; WebAssembly Component Model/WIT; GraalVM interoperability; Rust ownership; Lean/Dafny correctness obligations. Borrow the techniques only where measurements show a gain.
