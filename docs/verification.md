# B verification: what is checked and what is assumed

B aims to make important error classes impossible to accept while accurately reporting everything it has not established. **Passing `b check` is not proof that the program achieves its intended result.**

## Enforced checks in v0.3

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

For *each explicit property*, future B should distinguish `proved`, `disproved` and `unknown`. v0.3 currently uses a simpler distinction: static errors, warnings and trusted assumptions. A built-in foreign signature or a successful type guard is **not** a machine-checked behavioral proof.

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
