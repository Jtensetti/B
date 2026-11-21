# B architecture

## Target

A new programming language with defined semantics and a compiler/runtime that reuses foreign ecosystems through typed adapters. The future machine-facing representation should optimize **total cost per independently correct result**, not merely source length.

## Implemented pipeline (v0.3)

```text
.bee source (.bsrc / .b compatible)
        |
        v
B Lark grammar -> B Expr/Stmt syntax tree
        |
        v
B checker: names, types, known constants, conditions
        |                              \
        |                              +-- diagnostics, assumed foreign contracts
        v
Python AST lowering (backend implementation, NOT B syntax)
        |
        v
Python bytecode -> CPython libraries
        |
        +-------------> typed JSON-lines .NET host
                          System.Math and Regex.IsMatch
```

- Native B `if` expressions and single-assignment bindings are part of the language, not agent-workflow instructions.
- Foreign `py:` calls can use discovered `.pyi` / `.py` signatures, built-in recognized signatures or explicit B `foreign` declarations. Unknown signatures become dynamic and are rejected in strict mode.
- The .NET bridge reflects permitted methods to a checked-in signature manifest verified in CI, and exposes only registered methods. B source declarations cannot change the adapter's executable allowlist.
- `b check --json` makes diagnostics and foreign assumptions machine-readable for future language-model tooling.
- `.bee` is the preferred extension; `.bsrc` and `.b` are compatible legacy forms.

This is **not yet** a native ahead-of-time compiler. B lowers to Python AST. Its type checker is incomplete, and its runtime is not isolated from malicious foreign code.

## Proposed design beyond v0.3

1. **Canonical typed B IR:** operation graph with versioned serialization and semantics independent of Python AST.
2. **Verified B core:** independent, small proof checker and explicit behavior contracts; track exactly which statements are proved, disproved and unknown.
3. **Generated interfaces:** Python `.pyi`, .NET assembly metadata, C ABI, Rust bindings and Wasm component/WIT produce version-pinned signatures with provenance and conversion rules.
4. **Runtime bridges:** keep native data inside its home runtime; share array/handle data only when lifetime and ownership are controlled.
5. **Model-facing API:** compact serialization for the *same* IR, grammar/type-constrained generation and structured corrections. Measure its value against strong native-language baselines before optimizing a tokenizer.

## Trusted computing base

B's parser, checker, lowering, runtime guard and FFI adapters are all trusted implementation components. Any defect in them can invalidate a check. No third-party library becomes verified merely by being imported. Differential testing and later a small proof checker can reduce—but not magically eliminate—these assumptions.

## Relevant systems to evaluate

MLIR and LLVM intermediate representations; WebAssembly Component Model/WIT; GraalVM interoperability; Rust ownership; Lean/Dafny correctness obligations. Borrow the techniques only where measurements show a gain.
