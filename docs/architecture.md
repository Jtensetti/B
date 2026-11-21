# B architecture

## Goal

Design **one genuinely new source language** whose compiler and type system can reuse foreign packages through explicit, inspectable interfaces. Optimise **total cost per independently verified successful programming task**, including model tokens, retries, compilation, runtime and adapter overhead. Do not optimise for minimal source length in isolation.

## Implemented pipeline (v0.1)

```text
B UTF-8 source
      |
      v
Lark grammar / parser ---> B model.Expr / model.Stmt
                                  |
                                  v
                    B type and constant checker
                         |             |
                 errors/warnings     typed program
                                       |
                                       v
                           Python AST lowering
                                       |
                                       v
                                Python bytecode
                                  /       \
                         CPython modules   .NET 10 host
                                             JSON lines
                                          System.Math subset
```

This is an interpreter/compiler prototype, not a native B backend. It deliberately uses existing library runtimes rather than translating foreign source code. The Python lowering is an implementation technique; Python syntax is **not** the language definition of B.

## Proposed architecture beyond v0.1

1. **Typed canonical IR.** B operations, bindings, effects, resources and ownership rules are represented without source-language-specific AST nodes. The IR must have a formal operational semantics, versioned serialization and reproducible builds.
2. **Compiler/verifier core.** Syntax checking, type inference, effect checking, incremental dependency analysis, contracts, optional proof checking, and diagnostics operate on this IR. A compiler error must identify the violated rule; an unknown proof obligation must not be labeled success.
3. **Adapter generator.** Extract Python type stubs, .NET metadata, C/Rust ABIs, and WebAssembly component interfaces into explicit B signatures with provenance, versions, cost, permitted effects and marshaling rules. No arbitrary behavior can be proven from signatures alone.
4. **Backend selection.** Initially Python + .NET bridge; later native and Wasm component backends. Prefer keeping data in its native runtime. Crossing a boundary should be explicit in cost estimates and may require a conversion or handle ownership policy.
5. **Incremental change model.** Make the canonical IR addressable by stable IDs, so a model may edit exactly one node with version checks and rerun only impacted analyses. This is a future language-tooling feature, not the language itself.

## Non-goals

- Guessing foreign-library semantics through language-model intuition.
- Treating JSON transport as a zero-copy foreign ABI.
- Promising arbitrary third-party libraries are free of bugs.
- A syntax designed only to minimize punctuation or characters.
- Hiding runtime warnings behind a green `check` label.

## Trusted computing base

B's checker, lowering, runtime guards and adapter implementations are trusted components. A false signature, bug in B's checker, or nonconforming adapter invalidates relevant guarantees. Runtime dependencies are **not** automatically proof-carrying. Differential tests and independent reference implementations are future requirements.

## References to evaluate, not directly copy

- WebAssembly Component Model + WIT for shared type-level interfaces and canonical ABI.
- MLIR and LLVM for typed, optimizable intermediate representations.
- GraalVM's polyglot interoperability for cross-language value semantics.
- Rust ownership and effect systems; Lean/Dafny for independently checkable proofs.

A project should only adopt parts that survive integration, performance and correctness benchmarks.
