# BIR v2 — B's typed semantic representation

## Status and goal

**BIR introduced in B 0.5; contracts and effects added in B 0.6.** BIR is the language's backend-independent, typed intermediate representation. It is deliberately *not* Python AST or a textual Python translation. The B checker turns parsed expressions into typed operations, then the Python lowering backend compiles **those operations** to a Python AST. BIR is also exposed as JSON via `b ir`.

BIR is an intermediate compiler artifact; its JSON output is intended for **inspection**, not for trusted code execution. We do not currently deserialize external BIR as executable programs: a malicious JSON document could otherwise forge type checks. A future BIR loader needs independent structural and type verification before execution.

## Pipeline

1. The B grammar yields syntax-only `Expr`/`Stmt` objects.
2. The checker resolves names, types and foreign signatures and creates `ExprIR`/`StmtIR` objects.
3. All referenced typed foreign functions appear in a `ForeignCatalog` with provenance and explicit backend; their behavior is always marked **unverified**.
4. `optimizer.optimize` performs strictly local pure literal simplifications. It neither executes nor reorders foreign calls and never removes boundary guards.
5. `PythonLowerer` translates the resulting BIR to Python AST, using distinct Python and .NET runtime adapters.

## Operations

| IR category | Current op names | Notes |
| --- | --- | --- |
| Basic | `literal`, `name`, `list`, `dict`, `attr` | Each expression has an explicit B type |
| Data | `guard`, `coalesce` | Runtime B type guard is explicit; `coalesce` evaluates its left operand once |
| Logic | `conditional`, `and`, `or`, `not`, `cmp` | Short-circuit order is preserved |
| Arithmetic | `add`, `sub`, `mul`, `div`, `mod`, `neg` | Retains B's existing Python-backed arithmetic semantics |
| Invocation | `call` | A known foreign target records its exact path, e.g. `net:System.Math.Sqrt` |
| Statements | `permit`, `import`, `foreign`, `let`, `fn`, `print`, `assert` | Imports carry an adapter and the exact module/type path |

`ProgramIR` has `schema: "bir"` and `version: 2`, together with `statements`, `foreign_symbols`, `assumed_foreign_contracts` and `behavior_proven: false`. This is intentionally not a comprehensive serialization protocol for all future B versions.

Example:

```text
use py:statistics as stats
print stats.mean([1.0, 3.0])
```

The `call` has B return type `Float` and foreign path `py:statistics.mean`. The catalog records its `List[Float] -> Float` **assumed** signature. A runtime guard checks the shape and type of the returned value. Neither that check nor the manifest proves the algorithm returns a mathematically correct mean.

## Boundaries and guarantees

- B types and native expressions belong to the B checker; the foreign adapter only controls **how** external code is called.
- BIR records typed external calls, not the translated source code of imported libraries.
- Unrecognized Python members may remain dynamic in non-strict mode. Their BIR call is tagged with a foreign path but has no assumed static signature. `--strict` refuses associated unresolved warnings.
- All `System.Math` / `Regex` signatures come from the currently small, allowlisted .NET host metadata. `net:` does **not** grant access to arbitrary .NET assemblies.
- FFI execution is outside the formal checking boundary. Side effects, library versions and external behavior are not established by the BIR type.
- The compiled output is Python bytecode through Python AST, not a native executable. Other backends are research proposals.
- The optimizer reduces only known-pure native literal expressions. Runtime checks and external calls remain in place, including for branches not statically selected.

## Commands

```sh
b ir examples/polyglot.bee --strict
b ir examples/polyglot.bee --optimized
b build examples/polyglot.bee
```

The unoptimized BIR retains the original checked expression tree; `--optimized` displays the BIR passed to the Python code generator.

## Additional BIR v2 fields

`ProgramIR` now includes `permitted_effects` (`null` when not declared) and `detected_effects`. Each function statement may include `declared_pure`, inferred `effects`, checked `requires` and `ensures` expressions, and `postcondition_status` of `proved-interval` or `runtime-check`. These fields are part of the checked IR, not comments injected into generated Python. The Python backend emits and preserves runtime checks from BIR.

A proof status applies **only** to that explicit predicate, under the function's `requires` assumptions. The `behavior_proven: false` program-level flag remains deliberately false. See [contracts and effects](contracts-effects.md).

## B 0.7 Python source adoption

`adopt py:MODULE.function as alias` produces an ordinary **native** BIR function with the checked function body. Its statement retains `backend: "py-source"` and `target: "py:MODULE.function@sha256:..."` for provenance. This is intentionally different from a `foreign_symbols` entry: the compiled program executes the B function, not an external Python callable. A SHA digest identifies read source bytes but is not a certificate that the original Python algorithm is correct. `behavior_proven` stays `false`. Unsupported source is rejected rather than being reclassified as pure. See [source adoption](source-adoption.md).

B 0.8 adds an optional `constant_precondition_proved` marker to a native call in BIR v2. It records a compiler check after scalar boundary conversion. The per-site contract report is computed on checked, unoptimized BIR. See [contract analysis](composition.md).

## Collection expressions in B 0.16

A `summarize` node has result type `Dict[Text,Int]`. Operand zero is the input list. Each ordered entry in `value.fields` contains the output name, reducer, value operand index, guard operand index and empty default. An unused slot is null. `value.binder` names the local element shared by the fields. A backend must evaluate the source once, visit each element in order and evaluate guarded values only on matching elements. Item membership is fixed at the start of the traversal. Updates to objects inside the list can still be visible to following field expressions. A backend can read the list length for an unconditional count. A `lookup` node holds a dictionary and a text key as operands and returns an optional value.

## Ordered counts in B 0.17

`history_count` returns `Int`. Its operands are the list source and the typed pair predicate. Its data contains the source names for the historical and current binders, the match mode and the selected plan. `past_side` identifies which projected operand uses the historical binder in specialized plans. For prefix extrema, `comparison` gives the operator when comparing the retained past value on the left against the current threshold. The optimizer determines the plan again after simplifying the predicate. Raw and optimized BIR thus describe their own executable operands.

For a strict prefix with integer projections, an earlier value exceeds a threshold exactly when the maximum of that nonempty prefix exceeds it. An empty prefix yields no match. Testing before extending the prefix keeps the current event out of its own history. A [separate induction argument and translation check](../experiments/ordered-history/loop-proof.md) cover the emitted loop for one Boolean adjacent-pair program.

## Executable changes in B 0.18

`also` lowers to typed comparisons and a conditional in the existing Boolean function. The checker validates each `keeping` clause on the unoptimized dependency graph. Revising an independently implemented program uses the accepted source plus the declaration as the reference. For 32 or more exact scalar tuples the Python backend can compile the same check into a constant membership index. [Semantics and comparison](executable-changes.md) · [Lookup measurements](../experiments/executable-changes/indexed/README.md).
