# B

**An experimental programming language that combines existing software ecosystems without forcing them into one language.** B has its own parser, types, static checks and compiler pipeline; its implementation currently lowers B to Python AST/bytecode and calls a small real .NET host for selected foreign methods.

**Version 0.4.** Canonical source extension: **`.bee`**. `.b4` is an optional playful alias; `.bsrc` and `.b` remain accepted. B is unrelated to the 1960s Bell Labs B language.

> This is a working *prototype*, not a universal compiler, a security sandbox, or a mathematically proved programming system. `b check --strict` means only the implemented static rules and constraints were satisfied. Imported libraries' behavior remains an external assumption.

## B 0.4: more libraries, fewer guesses

```text
use py:b_examples.poly_lib as lib

let label: Text = lib.describe("b")
let number: Int = lib.describe(41)
let possible: Option[Int] = lib.find_code("Ada")
let doubled: Dict[Text, Float] = lib.adjust({"a": 2.0, "b": 3.5})

print label
print number
print possible
print doubled
```

This is **B syntax**, not Python. B discovers two `@overload` variants of `describe` in the adjacent Python stub, picks the unambiguous variant from the B argument types and checks its return type during execution. The `Option` and `Dict` types are also first-class B types. The sample calls a real, installed Python module. B can refuse ambiguous calls before any user program is executed.

## Polyglot call to .NET and Python

```text
use py:statistics as stats
use net:System.Math as Math
use net:System.Text.RegularExpressions.Regex as Regex

let valid: Bool = Regex.IsMatch("B-42", "^B-[0-9]+$")
let average: Float = stats.mean([3.0, 4.0, 5.0])
let answer: Float = if valid then Math.Sqrt(average * average + 9.0) else 0.0
print answer
```

The .NET host permits a narrow set of Math and Regex methods and communicates with the B runtime via typed JSON lines. This is **not** a generic .NET binding. The Python `statistics.mean` call is from the actual standard library.

## Install and try

Python 3.11+ and `pip` are required; .NET examples and full cross-runtime CI also require the **.NET 10 SDK**.

```sh
python -m pip install -e '.[dev]'
b check examples/polytypes.bee --strict --json
b run examples/polytypes.bee
b check examples/polyglot.bee --strict
b run examples/polyglot.bee
b inspect py:b_examples.poly_lib --json
b inspect net:System.Math --verify  # requires .NET 10
b check examples/hello.b4 --strict
pytest -q
```

B `b check` parses and checks B code without running it. Python import discovery may execute parent package initializers in dotted imports, and `b run` executes foreign code with the current process's permissions. Do not treat this as a sandbox.

## Implemented versus planned

| Area | Implemented in 0.4 | Still missing |
| --- | --- | --- |
| Language | Let, typed functions, if, collections, booleans, arithmetic | Loops, records, modules, generic B functions |
| Types | `Int`, `Float`, `Text`, `Bool`, `Any`, `Option`, `List`, `Dict` | Full unions, Result, pattern matching, objects |
| Python ecosystem | Real imports; limited non-executing `.pyi`/`.py` AST discovery; basic overload selection | Broad typeshed, keyword-only args, typevars, protocols |
| .NET ecosystem | Explicit Math/Regex adapter; metadata snapshot checked against live reflection in CI | Arbitrary packages, objects, generic methods |
| Verification | Types, arity, known constant errors, typed runtime boundaries | General behavioral proof, effects, isolation |
| Machine optimization | Machine-readable errors and library discovery | Measured model token savings, typed native IR, constrained decoding |

## Why B exists

The hypothesis is that an AI should write **less new code** by composing existing verified or well-specified operations, while a single language/compiler checks the parts of the composition it can actually know. We have **not** yet demonstrated that B beats Python on AI programming tasks. That comparison needs independent generated programs, matched budgets, real libraries, and behavioral tests.

## Documentation

- [Language specification](docs/language.md) — grammar, types, evaluation, diagnostics.
- [Interop and foreign assumptions](docs/interop.md) — Python/.NET integration and its trust limits.
- [Experiments](docs/experiments.md) — tests and what they do not establish.
- [Roadmap](docs/roadmap.md) — implemented vs planned.
- [File suffix rationale](docs/file-extension.md) — `.bee`, `.b4`, `.bi`, other collisions.
- [VS Code syntax support](editors/vscode/b-language) — optional local highlighting extension.

MIT licensed.
