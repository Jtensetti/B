# B

**B is a small experimental programming language with its own grammar, type checker and compiler. It calls real libraries across language runtimes instead of requiring them to be rewritten.**

**Current version: 0.3 (experimental). Source files use `.bee`.** B is not a scripting alias for Python, not an agent framework, and not a proof of the correctness of arbitrary imported code. The compiler currently lowers B into Python AST/bytecode; selected .NET calls run through a separate typed .NET 10 process.

## A polyglot B program

```b
use py:statistics as stats
use net:System.Math as Math
use net:System.Text.RegularExpressions.Regex as Rx

let valid: Bool = Rx.IsMatch("item-42", "^item-[0-9]+$")
let avg: Float = stats.mean([3.0, 4.0, 5.0])
let score: Float = if valid then Math.Sqrt(avg * avg + 9.0) else 0.0
print score
```

The `.NET` methods in this example are implemented in the [B .NET host](dotnet/B.NetHost/Program.cs); the Python function is from the installed standard library.

## New in 0.3: automatically discover Python library signatures

```b
use py:examples.demo_lib as tools

let result: Float = tools.clamp(12.0, 0.0, 10.0)
let message: Text = tools.repeat("B", 3)
print message
print result
```

B finds the adjacent [`demo_lib.pyi`](examples/demo_lib.pyi), reads its typed function declarations *as syntax*, and registers supported positional signatures automatically. No B `foreign` declarations or compiler registry edits are necessary. If a `.pyi` is absent, B can recognize a conservative subset of `.py` function annotations. B refuses to guess unrepresentable types or overload sets. It **does not execute the Python module while extracting the signatures**; Python's module discovery may nevertheless import *parent packages*.

For imported functions with unknown signatures, non-strict checks still warn; `--strict` rejects unresolved warnings. Explicit `foreign` declarations remain available for such functions.

## Install and run

Requires Python 3.11+. The cross-runtime example also requires the **.NET 10 SDK**.

```sh
python -m pip install -e '.[dev]'
b check examples/auto_discovery.bee --strict
b run examples/auto_discovery.bee
b check examples/polyglot.bee --strict
b run examples/polyglot.bee
pytest -q
```

Inspect what B actually knows about the libraries:

```sh
b inspect py:examples.demo_lib
b inspect net:System.Math
b inspect net:System.Math --verify    # requires .NET SDK, compares live reflection with manifest
b check examples/auto_discovery.bee --strict --json
```

The checked-in [`.NET metadata snapshot`](b_lang/net-signatures.json) is consumed during normal `b check` without requiring .NET. CI builds the .NET host and compares the snapshot with signatures obtained from live CLR reflection. The snapshot covers only the .NET host's explicitly permitted `System.Math` and `Regex.IsMatch` methods. It is **not** generic .NET interop.

## What is actually implemented?

| Feature | Status |
| --- | --- |
| B parser, syntax tree, expression functions, `let`, `if`, lists, operators | Working subset |
| B static checks for types, function arity, certain constant failures | Working subset |
| Automatic `.pyi` / typed `.py` signature extraction | Working for simple top-level positional functions; unsupported shapes skipped |
| Real Python library calls | Working; Python retains its own runtime |
| .NET callable host + CLR metadata inspection | Working for six permitted method signatures; CI checks snapshot drift |
| Runtime checks on imported values | Implemented for existing B types, not a security sandbox |
| Structured error output `b check --json` and metadata `b inspect` | Working |
| General proof of program behavior, arbitrary .NET, Java/Rust/Wasm, native compilation | Not implemented |

`--strict` **does not mean proven behavior**. It means all currently defined static obligations have been resolved; metadata and manually declared foreign signatures are listed as **assumptions**. Unknown side effects, wrong but correctly typed library results and environmental failures remain possible.

## File extension

`.bee` is the preferred source filename suffix from v0.3. `.bsrc` and `.b` remain accepted for existing projects. `.be` is **not** used because it belongs to the Berry language. `.bee` is not globally exclusive either: other software, including BeeSchema, uses it. [Rationale](docs/file-extension.md).

## Documentation

- [Language reference](docs/language.md): syntax, types, evaluation and diagnostics
- [Cross-language metadata and trust boundaries](docs/interop.md)
- [Architecture](docs/architecture.md), [verification scope](docs/verification.md) and [experiments](docs/experiments.md)
- [Roadmap](docs/roadmap.md) and [long-term B 1.0 proposal](docs/design-b1.md)
- [VS Code syntax highlighting](editors/vscode/b-language)

B is MIT-licensed, independently developed and unrelated to the original Bell Labs B language.
