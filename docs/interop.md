# Cross-language interoperability in B 0.3

B's value proposition is reuse of existing software. It does not translate Python or .NET implementations into B, and imported behavior is not formally verified.

## Python metadata discovery

For `use py:package.module as alias`, the compiler resolves the module and searches for an adjacent `.pyi` stub. If none is present, it reads the `.py` module source. It parses this text with Python's AST library and collects a deliberately small subset of top-level `def` signatures.

Understood annotations: `int`, `float`, `bool`, `str`, `Any`, and `list[T]` / `List[T]` where T is supported. Positional arguments and trailing defaults work. Async functions, arbitrary decorators, `*args`, keyword-only parameters, Union/Optional, generic overload sets, methods nested in classes, unsupported return values and signatures with missing types are skipped — **not guessed**.

```b
use py:examples.demo_lib as tools
let score: Float = tools.clamp(12.0, 0.0, 10.0)
```

`b inspect py:examples.demo_lib --json` shows each discovered function, its signature and the source (`pyi` or `py`). When a typed function is called, `b check --json` records an assumed foreign signature. A known function that receives a wrong B type fails before execution; actual arguments and return values are also checked at the boundary.

**Threat and correctness model:** extracting signatures does not execute the target module or evaluate annotation expressions. However, Python's `find_spec` can import *parent packages* for dotted names. `b run` imports and runs library code, which can perform arbitrary I/O. The Python parser, filesystem and package installation are trusted in this prototype; no sandbox is provided. Stubs can be inaccurate or malicious. Type guards cannot detect incorrect results with the correct types. Signature discovery is not behavioral verification.

## Explicit foreign declarations

```b
use py:statistics as stats
foreign stats.median(List[Float]) -> Float
print stats.median([1.0, 3.0, 7.0])
```

Use when automatic discovery cannot represent the signature. Explicit declarations describe the B boundary but are **trusted claims made by the author**, checked only for type compatibility at runtime. A declaration cannot override a known built-in or auto-discovered signature.

## .NET reflection and a permitted transport

The .NET 10 host has a narrow allowlist of static functions. `B.NetHost --describe` enumerates **real CLR metadata via reflection** and returns their transport-compatible B signatures. The generated [`net-signatures.json`](../b_lang/net-signatures.json) is tracked in Git and used for static checks without starting .NET. CI verifies that its contents match current reflection output.

- `System.Math`: `Sqrt`, `Pow`, `Abs`, `Min`, `Max` with `Float` arguments and results.
- `System.Text.RegularExpressions.Regex`: `IsMatch(Text, Text) -> Bool`; the host uses a 250 ms matching timeout.
- Calls cross a JSON-lines process boundary. Complex CLR objects, generics, callbacks and zero-copy buffers are not supported.
- Reflection is used only to describe **allowed** methods, never to authorize an arbitrary method at runtime.
- Live introspection: `b inspect net:System.Math --live`. Metadata drift check: `b inspect net:System.Math --verify`.

## Planned other ecosystems

| Runtime | Proposed entry point | Major unresolved problem |
| --- | --- | --- |
| Rust and C | C ABI or WebAssembly/WIT | Ownership/lifetime and unsafe pointers |
| Java | JVM metadata and isolated adapter | Object handles, overloads and concurrency |
| WebAssembly | Component Model/WIT | Full component ABI/runtime and resource transfer |
| Arbitrary .NET | Versioned metadata, generated permission-scoped adapter | General overloads, properties, object lifetimes and side effects |
| Python ecosystem at scale | Typeshed and installed typing metadata | Complex annotations, overloads, side effects and version drift |

A safe and useful general B FFI requires explicit capabilities, effect semantics, nullable/variant/record types, a versioned type schema and targeted adapters. These are research tasks, not accomplished by v0.3.
