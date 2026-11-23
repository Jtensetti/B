# Cross-language interoperability in B

B's value proposition is reuse of existing software. The linked libraries execute in their respective runtimes. Foreign signatures describe expected values, and the adapters check values at their boundaries.

## Python metadata discovery

For `use py:package.module as alias`, the compiler resolves the module and searches for an adjacent `.pyi` stub. If none is present, it reads the `.py` module source. It parses this text with Python's AST library and collects a deliberately small subset of top-level `def` signatures.

Understood annotations: `int`, `float`, `bool`, `str`, `Any`, and `list[T]` / `List[T]` where T is supported. Positional arguments and trailing defaults work. Async functions, arbitrary decorators, `*args`, keyword-only parameters, Union/Optional, generic overload sets, methods nested in classes, unsupported return values and signatures with missing types are skipped — **not guessed**.

```b
use py:b_examples.demo_lib as tools
let score: Float = tools.clamp(12.0, 0.0, 10.0)
```

`b inspect py:b_examples.demo_lib --json` shows each discovered function, its signature and the source (`pyi` or `py`). When a typed function is called, `b check --json` records an assumed foreign signature. A known function that receives a wrong B type fails before execution; actual arguments and return values are also checked at the boundary.

**Threat and correctness model:** extracting signatures does not execute the target module or evaluate annotation expressions. B follows package search locations without running filesystem package initializers. The Python environment's import finders and path hooks remain trusted. `b run` imports and runs library code, which can perform arbitrary I/O. The Python parser, filesystem and package installation are trusted in this prototype; no sandbox is provided. Stubs can be inaccurate or malicious. Type guards cannot detect incorrect results with the correct types. Signature discovery is not behavioral verification.

## Explicit foreign declarations

```b
use py:statistics as stats
foreign stats.median(List[Float]) -> Float
print stats.median([1.0, 3.0, 7.0])
```

Use when automatic discovery cannot represent the signature. Explicit declarations describe the B boundary but are **trusted claims made by the author**, checked only for type compatibility at runtime. A declaration cannot override a known built-in or auto-discovered signature.

## A call that can fail

```b
use py:tariff as tariff
foreign tariff.zone(Text) -> Option[Int] on KeyError
let zones = [tariff.zone(c) ?? 0 for c in countries]
```

B has no `try`. A foreign function that raises an exception for some inputs is declared with the exceptions it may raise and an `Option` result, and the call gives `none` when one of them is raised. Exceptions are matched by class name along their hierarchy, so `on LookupError` also catches `KeyError`, and a library's own exception class needs no import. Any other exception still stops the program. The declaration restates the signature B read from the library: the parameters and the type inside the `Option` must match it. It works for Python only. npm and .NET errors are not mapped yet.

## .NET reflection and a permitted transport

The .NET 10 host has a narrow allowlist of static functions. `B.NetHost --describe` enumerates **real CLR metadata via reflection** and returns their transport-compatible B signatures. The generated [`net-signatures.json`](../b_lang/net-signatures.json) is tracked in Git and used for static checks without starting .NET. CI verifies that its contents match current reflection output.

- `System.Math`: `Sqrt`, `Pow`, `Abs`, `Min`, `Max` with `Float` arguments and results.
- `System.Text.RegularExpressions.Regex`: `IsMatch(Text, Text) -> Bool`; the host uses a 250 ms matching timeout.
- Calls cross a JSON-lines process boundary. Complex CLR objects, generics, callbacks and zero-copy buffers are not supported.
- Reflection is used only to describe **allowed** methods, never to authorize an arbitrary method at runtime.
- Live introspection: `b inspect net:System.Math --live`. Metadata drift check: `b inspect net:System.Math --verify`.

## Node.js and npm (B 0.12)

`use js:"node:path/posix" as path` gives B six static signatures for POSIX path operations. `use js:semver as versions` provides typed signatures for 21 functions: `satisfies`, `compare`, `valid`, `maxSatisfying`, `minSatisfying`, `clean`, `validRange`, `prerelease`, `gt`, `gte`, `lt`, `lte`, `eq`, `major`, `minor`, `patch`, `sort`, `rsort`, `diff`, `inc` and `intersects`. `use js:"fastest-levenshtein" as words` provides `distance` and `closest`. At execution B checks that the installed semver package is version 7. Inspect the catalog with `b inspect js:semver --json`. The catalog is available during compilation without starting Node or loading npm code.

For a different installed package, quote scoped or hyphenated names and declare the synchronous export to be called:

```bee
use js:"fastest-levenshtein" as words
foreign words.closest(Text, List[Text]) -> Text
print words.closest("Trellebog", ["Trelleborg", "Lund", "Malmö"])
```

The Node process resolves packages from the B source's directory on `b run`. A generated Python file resolves from its own directory at execution. Calls within one execution share module state. Each JSON-compatible value is copied across the boundary. Supported B types are `Text`, `Bool`, safe `Int`, finite `Float` and supported nested `Option`, `List` and string-keyed `Dict` values. JavaScript safe integers run from −(2⁵³−1) through 2⁵³−1. Promises, callbacks, class instances, buffers and BigInt require other interfaces. Foreign effects follow B's normal effect rules. Imported code runs with the process's operating-system permissions.

The installed-package tests use two independently published packages and an uncurated named export. The three-runtime example uses Python to decode an artifact path, .NET to check its release channel and JavaScript to check the version range. [Examples and measured coverage](../experiments/node-interop/README.md).

## Planned other ecosystems

| Runtime | Proposed entry point | Major unresolved problem |
| --- | --- | --- |
| Rust and C | C ABI or WebAssembly/WIT | Ownership/lifetime and unsafe pointers |
| Java | JVM metadata and isolated adapter | Object handles, overloads and concurrency |
| WebAssembly | Component Model/WIT | Full component ABI/runtime and resource transfer |
| Arbitrary .NET | Versioned metadata, generated permission-scoped adapter | General overloads, properties, object lifetimes and side effects |
| Python ecosystem at scale | Typeshed and installed typing metadata | Complex annotations, overloads, side effects and version drift |

A safe and useful general B FFI requires explicit capabilities, effect semantics, nullable/variant/record types, a versioned type schema and targeted adapters. These are research tasks, not accomplished by v0.3.

## B 0.4: supported Python overload, Option and Dict signatures

The discovery reader now supports a **small explicit subset** of `@overload` sets and nullable, dictionary annotations. It never calls Python's `eval` or `get_type_hints` on untrusted annotation expressions. A call with ambiguous return contracts is rejected rather than guessed. See [`examples/polytypes.bee`](../examples/polytypes.bee).

- `int | None`, `Optional[int]`, `Union[int, None]` map to `Option[Int]`.
- `dict[str, float]` maps to `Dict[Text, Float]` and is recursively checked at typed boundaries.
- `@overload` choices are selected by supported argument types; `Any` with ambiguous alternatives is rejected.
- `b inspect py:b_examples.poly_lib --json` shows all supported variants, and all are **assumed interfaces** rather than proven behavior.
- Unsupported annotations such as `TypedDict`, complex unions, `TypeVar` and keyword-only signatures remain unknown. B does not silently pretend they are supported.

## BIR and library coverage in v0.5

`b_lang.interop.ForeignCatalog` uses a common `ForeignSymbol` representation for discovered Python functions and .NET host metadata. A typed call retains its adapter (`py` / `net`), full foreign name, assumed signature and provenance; `behavior_proven` remains false. `b ir` displays only the typed external functions actually called. The Python backend then lowers those references to the existing CPython importer or allowlisted .NET host.

`b audit py:MODULE` reports a narrowly defined *direct public function declaration* coverage metric, **not** a package-level completeness claim. The 2026-11-21 observation found almost no support for large scientific libraries' complex public annotations. See [the full audit](library-audit.md). The compiler still allows dynamic Python calls in non-strict mode, but that is not equivalent to statically checked compatibility.

## Checked source adoption (B 0.7)

Separate from `use`, the `adopt py:MODULE.function as local` operation may statically translate a tiny single-expression Python function into an ordinary native B function. No Python module import is emitted. A source SHA-256 appears in the BIR function origin; unsupported constructs are rejected. The tool does not claim that arbitrary Python code is pure or behaviorally verified. See [source adoption and coverage](source-adoption.md).

## Objects from another language

`foreign type Date = dt.date` names a Python class as an opaque B type. `foreign Date.isocalendar() -> List[Int]` declares a method. B type checks every call to a declared method and guards its result at runtime. It never reads the object's attributes directly. Each method appears in the compiler's assumptions, because its signature is declared, not read. A Python tuple returned at the border becomes a `List`.

