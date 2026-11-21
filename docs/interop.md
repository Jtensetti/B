# Interoperability model

B does **not** reinterpret a Python library as C# or vice versa. B exposes a *foreign function* with an explicit signature and dispatches the call to its native runtime.

## v0.1 `py:` imports

- `use py:statistics as stats` resolves an installed module.
- Registered function signatures are checked statically. The known return type is guarded at runtime.
- Unknown Python functions return B `Any` and generate `W_UNCHECKED_FOREIGN` when called.
- `--strict` rejects such calls, but does not verify the internals of known functions.
- Python imports may run arbitrary Python code, access files and execute side effects. **This is not a sandbox**.

## v0.1 `net:` imports

- `use net:System.Math as Math` binds a proxy.
- Calls are transmitted as JSON lines to a persistent .NET 10 process built from `dotnet/B.NetHost`.
- Only `System.Math.Sqrt`, `Pow`, `Abs`, `Min` and `Max` are allowlisted.
- The host only accepts finite JSON numbers for these methods and returns finite JSON numeric results.
- Other types, methods and assemblies are rejected, not guessed.
- Runtime guards validate declared B types on returned values.

This interface **copies and serializes** data. It cannot directly share object references, callbacks, large arrays or arbitrary CLR objects. It is slow for many tiny calls and unsuitable for high-throughput numeric arrays without a redesigned transport.

## Where a large library ecosystem could come from

| Ecosystem | Likely adapter approach | Key difficulty |
| --- | --- | --- |
| Python | CPython FFI, type stubs, introspection, handles | Dynamic types, arbitrary effects, reference ownership and GIL |
| .NET | Metadata plus in-process managed hosting or sidecars | CLR object lifetimes, generics, async, overloads |
| Rust | Exposed C ABI or Wasm component interfaces | Lifetime and ownership contracts; Rust source is not a stable ABI |
| Java | JVM host with metadata-driven bindings | GC handles, overloads, reflection, asynchronous execution |
| C/C++ | C ABI or explicitly generated bindings | Pointers, undefined behavior, layouts and memory safety |
| WebAssembly | WIT / component model | Component and runtime feature compatibility |

A future B IR must represent at least numeric width, nullable values, text encoding, records, lists, results/errors, resource handles, async semantics and effects. `Int` is currently arbitrary-precision; converting it to a bounded foreign integer must require range checks. Float/decimal conversions must not silently lose guarantees.

## Trust tiers (proposed)

- `native-verified`: properties established within the supported B semantics.
- `contract-checked`: declared foreign signature, runtime guards, but unverified library behavior.
- `dynamic`: no static signature; usage explicitly warned or forbidden by policy.
- `proved`: machine-checked behavioral claim under stated assumptions (not implemented).

These tiers should attach to every imported symbol in future versions. A semantic contract or specification can be wrong and must have provenance and tests.
