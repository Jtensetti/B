# B interoperability v0.2

B connects to foreign runtimes through explicitly typed boundaries. Imported code retains its original implementation and licensing; B does **not** translate its source into B, and does not claim the foreign library is correct.

## Python: directly imported packages

```text
use py:statistics as stats
foreign stats.median(List[Float]) -> Float
let n: Float = stats.median([2.0, 4.0, 100.0])
```

- `use py:module as alias` finds and imports the *real* installed CPython package.
- A small built-in registry recognizes some signatures (`math`, `statistics`).
- `foreign alias.method(T1, T2) -> R` supplies an explicit signature for any callable exposed by an imported Python module. It does not modify the Python package.
- B type-checks the call, validates the foreign arguments immediately before dispatch, and validates the returned value against the declared B return type.
- `foreign` declarations are trusted assumptions about signatures, **not validated contracts about behavior**. The runtime may detect a mismatched return type, but cannot tell whether a correctly typed value is the correct answer.
- Without a signature, unknown Python members are dynamic with a `W_UNCHECKED_FOREIGN` warning. Strict mode rejects those warnings.
- Imports execute in the running Python process with its full privileges; they are neither sandboxed nor effect-checked.

## .NET: narrow typed process boundary

- B's .NET adapter is a persistent .NET 10 process communicating through typed JSON lines.
- Implemented types: `System.Math` (`Sqrt`, `Pow`, `Abs`, `Min`, `Max`) and `System.Text.RegularExpressions.Regex` (`IsMatch`).
- All method names are allowlisted in the adapter; B-source `foreign` declarations cannot extend this whitelist.
- Finite numeric values and text/bool results are checked. Regex evaluation is limited to 250 ms to constrain a common denial-of-service risk; this is not a sandbox or overall CPU limit.
- JSON transport loses shared object identity, requires copies and conversion, and is not zero-copy.
- External .NET methods that return an unexpected B type cause a boundary error. Exceptions are returned as host error messages.

## Why `foreign` matters

Previously, a user of a library not in B's small built-in signature registry had to choose unchecked dynamic calls or change compiler code. In v0.2 the B program can define its own signature. This expands the *reachable* Python API surface, but a false user declaration remains possible. Trusted metadata generation and version locking are future work.

## Planned high-coverage binding generation

| Ecosystem | Candidate strategy | Important limitations |
| --- | --- | --- |
| Python | Read trusted `.pyi` stubs and importable metadata; generate `foreign` manifests | Dynamic features, overloaded functions, arbitrary effects |
| .NET | Read assembly metadata; generate transport-safe typed adapters | CLR object identity, overload resolution, generics, async |
| Rust / C | Consume explicit C ABI, WIT, or generated bindings | Lifetimes, pointers and unstable native Rust ABI |
| Java | JVM metadata and process/in-process adapters | GC, handles, overloads, exceptions |
| WebAssembly | Component model/WIT type boundaries | Runtime support, resource semantics, transport |

A future stable B IR must handle fixed-width numbers, floats and decimals, nullability, records, results, resource handles, effects and asynchronous behavior. B 0.2 has none of these guarantees at the general level.
