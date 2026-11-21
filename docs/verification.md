# Verification is not a boolean

The ambition is to make large classes of errors impossible **without lying about what has been checked**. "Compiles" is not equivalent to "does what the user intended".

## Implemented checks

1. B grammar and known keyword structures.
2. Name resolution, duplicate top-level names and reserved names.
3. Primitive, list and function parameter/result types, with Int-to-Float widening.
4. Known foreign call arity and parameter types for the small registry.
5. Constant division by zero.
6. Statically false constant assertions.
7. Runtime guards for explicit annotations and known foreign return types.
8. Runtime assertions not erased by Python optimization flags.
9. `--strict` rejection of unresolved static warnings.

## Not implemented

- Whole-program formal verification.
- Side-effect analysis and effect-based import policy.
- Ownership, concurrency, data-race freedom or bounds on resources.
- Proofs of Python/.NET library implementations.
- Semantic equivalence of backends.
- Guaranteed runtime termination, deterministic execution or sandboxing.

## The three-way outcome

For any *specific* property, B should eventually distinguish `proved`, `disproved` and `unknown`. The current CLI instead reports errors and warnings. A recognized foreign signature is **an assumption**, not proof of the library behavior.

## Example

```b
let n = 3
assert n > 2  # the limited constant evaluator can establish this
```

But:

```b
use py:statistics as stats
let value: Float = stats.mean([1.0, 2.0, 3.0])
assert value > 1.0
```

The compiler recognizes the function signature and checks its returned type at runtime. It cannot prove the assertion using the current constant evaluator, and `b check --strict` rejects the unresolved obligation. Normal mode emits a runtime assertion.

## Source of truth and threat model

The project intentionally exposes foreign-library capability. Imported Python modules can perform arbitrary I/O. Input `.b` files are therefore **trusted programs**, not safe user scripts. The .NET adapter narrows exposed APIs but the Python execution backend is not isolated. An actual sandbox would require OS/container isolation, capability-based interfaces and separate threat-model validation.

## Research hypotheses

- Fewer generated decisions and narrower library calls reduce real failures and model-token cost.
- A typed canonical IR can make incremental verification practical.
- Automatically generated foreign metadata can improve access to libraries without a loss of auditability.
- A new source representation may outperform standard languages for selected models **after conditioning/training**, not automatically.

These are hypotheses to test, not claims of results.
