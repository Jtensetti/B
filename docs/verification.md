# B verification: what is checked and what is assumed

B aims to make important error classes impossible to accept while accurately reporting everything it has not established. **Passing `b check` is not proof that the program achieves its intended result.**

## Enforced checks (B 0.6)

1. B syntax, names, reserved names and duplicate bindings.
2. Static types for primitive values, lists, expression functions and both branches of conditional expressions.
3. Correct function arity for known signatures and B functions.
4. Constant division by zero and statically disproved assertions.
5. Runtime guards for explicit typed values, including heterogeneous values narrowed from `List[Any]` to `List[T]`.
6. Argument and return type checks across *declared or auto-discovered* foreign function boundaries.
7. `--strict` rejects unresolved warnings such as dynamic foreign calls or assertions that still need execution.
8. `b check --json` provides accepted/rejected status, diagnostics and explicit trusted foreign assumptions.

## What is not proved

- Correctness of the user's specification, or even the existence of a full behavior specification.
- Correctness of imported Python/.NET functions or user-authored `foreign` declarations.
- Effects, termination, absence of memory errors inside foreign code, concurrency properties, or resource bounds.
- Functional equivalence of future backends or absence of bugs in B's compiler.
- Safe execution of untrusted programs. Python code and libraries execute with the current account's privileges.

## The three outcomes we eventually need

For *each explicit property*, future B should distinguish `proved`, `disproved` and `unknown`. v0.6 currently uses a simpler distinction: static errors, warnings and trusted assumptions. A built-in foreign signature or a successful type guard is **not** a machine-checked behavioral proof.

## Example

```text
let n: Int = if true then 3 else 8
assert n == 3
```

The constant checker accepts both statements without running the program. But:

```text
use py:statistics as stats
foreign stats.median(List[Float]) -> Float
let value: Float = stats.median([1.0, 2.0, 3.0])
assert value > 1.0
```

The foreign method's return type is guarded at runtime; its mathematical behavior is not proved. The final assertion remains a runtime obligation and `--strict` rejects that obligation.

## Threat model

The codebase is an experimental **trusted-code toolchain**. The .NET host narrows its API surface, but B's Python backend can invoke arbitrary installed Python code. There is no isolation from the user's filesystem, processes, devices or network. Do not run programs from untrusted parties without external isolation.

## Added in B 0.4

- Statically reject ambiguous Python overloads (`E_OVERLOAD_AMBIGUOUS`) instead of treating the result as safely typed.
- Preserve nullability: `Option[T]` cannot silently be assigned to `T`. `??` permits a checked fallback and does not duplicate side-effecting calls.
- Recursively check `Dict[Text,T]`, `List[T]` and `Option[T]` at declared/foreign boundaries.
- Reject statically known heterogeneous list/dictionary literals before attempting execution.
- Importantly, these extend **type checking**, not behavioral verification of foreign libraries.

## B 0.5 IR correctness boundary

The typed BIR is created only after existing B checks. Its producer is trusted and its consumer is the Python AST backend. JSON output is informational; B does not accept untrusted JSON IR as executable input, avoiding type-forgery attacks by construction. The optimizer folds only pure literal operations and never evaluates or reorders imported calls or erases boundary guards. Regression tests check these assumptions for the implemented subset.

## Added in B 0.6

- `requires` and `ensures` are native B function clauses; no executable calls or ambient globals are allowed in contract expressions.
- A small integer interval checker reports `proved-interval`, rejects guaranteed false postconditions, and leaves harder properties as `runtime-check`. It does not claim to verify arbitrary algorithms, foreign code or Float arithmetic.
- Function input types, preconditions, return types and postconditions are checked again by runtime guards, even when compiled functions are called from Python.
- `pure` forbids statically classified external effects inside functions. `permit` restricts program-level `console`/`foreign` categories. Any unknown import is conservatively `foreign`, including initialization.
- **Neither `pure` nor `permit []` is a sandbox or a proof of effect freedom at OS level.** Strict mode requires resolution of warnings, but accepted code can still fail at runtime and use arbitrary resources through permitted foreign code.

See [the exact 0.6 rules](contracts-effects.md).
