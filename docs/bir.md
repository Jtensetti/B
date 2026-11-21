# BIR v1 — B's typed semantic representation

## Status and goal

**Implemented in B 0.5.** BIR is the language's backend-independent, typed intermediate representation. It is deliberately *not* Python AST or a textual Python translation. The B checker turns parsed expressions into typed operations, then the Python lowering backend compiles **those operations** to a Python AST. BIR is also exposed as JSON via `b ir`.

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
| Statements | `import`, `foreign`, `let`, `fn`, `print`, `assert` | Imports carry an adapter and the exact module/type path |

`ProgramIR` has `schema: "bir"` and `version: 1`, together with `statements`, `foreign_symbols`, `assumed_foreign_contracts` and `behavior_proven: false`. This is intentionally not a comprehensive serialization protocol for all future B versions.

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
