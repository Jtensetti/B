# B 0.6: native contracts, proofs and effect preflight

For cross-function analysis in 0.8, see [contract analysis and revision comparison](composition.md).

**Implemented experimental subset.** This document specifies the new v0.6 features as they actually run. B remains a research language and its checking is not a general verification or security system.

## 1. Why these features exist

A language that reuses other ecosystems needs to distinguish **what a function claims**, **what the checker proves**, and **what unknown imported code may do**. Without this distinction, `foreign` imports are mistaken for safe, verified operations.

This experiment borrows from the `requires`/`ensures` approach used by [Dafny](https://dafny.org/latest/OnlineTutorial/guide) and effect classification as in [Koka](https://koka-lang.github.io/koka/doc/index.html). B 0.6 implements only narrow portions of those ideas; neither their solvers nor their effect systems are part of B.

## 2. Syntax

```ebnf
permission  = "permit", "[", [identifier, {",", identifier}], "]" ;
function    = "fn", name, "(", [parameters], ")", "->", type,
              ["pure"], ["requires", expression], ["ensures", expression],
              "=", expression ;
```

One statement per line. `permit` may appear **only once, before any other statement**. The only supported categories are `console` (top-level printing) and `foreign` (any imported code, including import initialization). When `permit` is omitted, B preserves v0.5's unrestricted behavior; this is not recommended for code requiring a checked effect budget.

```bee
permit [console]
fn successor(x: Int) -> Int pure requires x >= 0 ensures result > 0 = x + 1
print successor(41)
```

Compiling with `b check examples/contracts.bee --strict --json` gives `detected_effects: ["console"]` and the function's postcondition status `proved-interval`. `b run examples/contracts.bee` prints `42`.

## 3. Effect checking

- Native arithmetic, literals, comparisons, typed containers, conditionals and pure B-function calls have no **externally observable effects tracked by B**.
- Every Python/.NET module import and foreign attribute access or function call is tagged **`foreign`**, irrespective of the signature's provenance. A foreign declaration never upgrades it to pure.
- Top-level `print` is tagged **`console`**.
- A B function's effect set includes effects of its body and calls to other B functions, even if the function is never invoked. A `pure` declaration refuses any classified external effect or nonconstant mutable global capture.
- `permit [...]` checks every statement and latent function body. A mismatch raises `E_EFFECT` **before B code executes**.
- Unknown foreign effects are **not** decomposed into read/write/network categories. `permit [foreign]` allows the entire unknown imported behavior, including any network or filesystem access it may perform.
- Exceptions, nontermination, timing, CPU, memory allocation, local mutation and possible data races are **not represented** in this effect model. `pure` is a limited *external-effects* promise, not a mathematical guarantee of totality or full referential transparency.
- Even `permit []` **is not a security sandbox**: compiler discovery and the Python lowering runtime are trusted code, and B does not create process isolation.

```
permit []
use py:math as m
```

The above is rejected as `E_EFFECT` because the import may execute Python initialization code.

## 4. Function contracts

`requires` is a **caller obligation** and is checked at runtime inside the function. If a call provides a constant expression that certainly violates `requires`, B rejects it immediately with `E_PRECONDITION`. If the compiler cannot determine whether an actual call meets the requirement, it emits `W_RUNTIME_PRECONDITION` and rejects the whole program in strict mode. Calling compiled B functions directly from Python still enforces runtime argument types and preconditions.

`ensures` is evaluated against a special read-only `result` identifier after the function body has computed and type-checked its return value. A failing runtime check raises `BContractError`. Both pre- and postconditions use a restricted **call-free**, side-effect-free Boolean grammar (literals, parameters, `result`, `+`, `-`, `*`, comparisons, `and`, `or`, `not`). They cannot import or invoke foreign code or silently read global variables. This makes contracts independent of side effects.

**A precondition is not automatically a proved fact about every caller.** A verified postcondition is conditional on that precondition holding; at runtime the guard enforces it. When evaluating a constant call statically, B normalizes scalar constants to the callee’s declared runtime parameter type first. For example, a large `Int` may round when passed to a `Float` parameter; the preflight checker must use the rounded value. Container values are intentionally not propagated as constants because guards may change their representation.

## 5. Deliberately narrow proof engine

The built-in analyzer does interval reasoning over arbitrary-precision **integer** parameters and integer results:

- Conjunctions of bounds such as `x >= 0 and x < 100` refine intervals.
- For integer results it can propagate intervals through literals, variables, addition, subtraction, unary minus, and bounded multiplication.
- It can conclude that supported comparisons must be true or false, even without running the program.
- When a postcondition is always false under the proven bounds, B raises `E_POSTCONDITION`.
- When it cannot establish the postcondition, it records `runtime-check` and issues `W_RUNTIME_POSTCONDITION`, which `--strict` refuses. Non-strict execution still evaluates the contract at runtime.
- For a verified postcondition, BIR records **`proved-interval`**. This is **not a whole-program proof**: neither imported libraries, absence of compiler bugs nor unspecific requirements are proved.
- Floating-point return results, including `Int -> Float` conversions, do **not** inherit integer proofs; rounding may change equality. Other unsupported cases remain runtime obligations.

### Three concrete outcomes

| B outcome | Example | Interpretation |
| --- | --- | --- |
| `proved-interval` | `requires x >= 0 ensures result > 0 = x + 1` (`Int`) | The simple integer consequence is proved for inputs satisfying `requires`. |
| `E_POSTCONDITION` | `requires x >= 0 ensures result < 0 = x + 1` | Every permitted integer input violates the contract. |
| `runtime-check` | `requires x >= 0 ensures result >= 0 = x - 1` | Some inputs may satisfy it, others violate it; non-strict mode checks each call at runtime. |

A guarantee can also be wrong because **the specification is wrong**. B cannot establish what the human or AI *intended* to request. The caller is responsible for independently specified behavior and, if desired, external isolation/tests.

## 6. BIR v2 representation

The checked internal representation now records:

- `ProgramIR.permitted_effects` (null if no declaration) and `detected_effects`.
- Per-function `effects`, `declared_pure`, `requires`, `ensures`, and `postcondition_status`.
- External function provenance remains an explicitly trusted assumption, not a proof.

`b ir FILE` exposes the verified structure without evaluating code. Runtime enforcement is lowered from these BIR nodes into Python AST. **BIR JSON is inspect-only**; it is never accepted as an executable input.

## 7. Evidence, failure cases and limitations

`tests/test_contracts_effects.py` includes preflight rejection, invalid call, unknown effects, strict rejection, runtime behavior, foreign provenance and float rounding regression cases. `tests/test_contracts_differential.py` uses seeded, bounded random integer contracts to compare accepted interval proofs with actual execution. This is an additional regression test, **not a proof of the verifier's soundness**.

What B 0.6 still lacks: effects for individual foreign operations (e.g., `network`), trusted proofs for library functions, any notion of sandboxing, SMT verification, termination proofs, theorem proof certificates, user-defined effect handlers and broad algorithm correctness verification.

**Research kill test:** Compare B against Python + static checkers + comparable runtime contracts on independently specified tasks and matched AI budgets. If B does not measurably reduce errors or end-to-end cost, this feature should not be presented as an AI advantage merely because it adds syntax.
