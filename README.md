# B

**A new programming language built to compose existing ecosystems — and say precisely what it can verify.**

B is an experimental, independently parsed and type-checked programming language. Its long-term goal is to let a machine generate concise, correct programs that reuse Python, .NET, Rust, Java and WebAssembly components without rewriting those libraries. It is **not** a prompt format, a multi-agent workflow, or a wrapper pretending that every imported program is proven correct.

> **Status: experimental v0.1.** A running B parser, typed expression language, checker and Python lowering exist. Python imports are real. The .NET bridge currently supports an explicit subset of `System.Math`. Rust, Java, generic .NET libraries, true ahead-of-time native compilation, proofs and AI token optimizations are **not** implemented. See [the language specification](docs/language.md) and [implementation status](docs/roadmap.md).

## First B program

```b
use py:statistics as stats
use net:System.Math as Math

fn twice(x: Float) -> Float = x * 2.0
let values = [3.0, 4.0, 5.0]
let average: Float = stats.mean(values)
let length: Float = Math.Sqrt(twice(average) * twice(average) + 9.0)
print length
```

This is B source, not Python or C#. The B compiler parses it into its own tree, checks native B types and recognized foreign signatures, then lowers it to Python. The imported `statistics.mean` is the actual Python standard-library function. The imported `System.Math.Sqrt` is executed by a real .NET process over a narrow, typed JSON-lines boundary.

## Try it

Requirements: Python 3.11+; for `.NET` examples also install the **.NET 10 SDK**.

```sh
python -m pip install -e '.[dev]'
b check examples/hello.b
b run examples/hello.b
b check examples/polyglot.b --strict
b run examples/polyglot.b
b build examples/polyglot.b  # inspect the Python lowering
pytest -q
```

`--strict` rejects unresolved static diagnostics. Passing it is **not** a proof that external libraries are correct; registered foreign signatures remain trusted assumptions and return values are checked at runtime.

## Language in 60 seconds

```b
# Comments start with #. Statements end at a newline.
use py:math as math
fn square(x: Float) -> Float = x * x
let radius: Float = 3.0
let area = math.pi * square(radius)
assert area > 28.0
print area
```

- `let` declares an immutable B binding in v0.1; types may be inferred or annotated.
- `fn` declares a typed, expression-bodied function.
- `use py:...` imports a real installed Python module; `use net:...` binds the allowlisted .NET adapter.
- `Int`, `Float`, `Bool`, `Text`, `Any`, and `List[T]` are the current types.
- `assert` is checked statically when the expression is constant, otherwise at runtime and reported as unproven.
- `b check` checks **without executing the B program**. It may inspect installed Python module availability.
- Unknown external Python methods are permitted in non-strict mode but produce a warning. **Strict mode refuses them**.

## What B means by “correct”

B distinguishes three claims that should never be conflated:

1. **Parsed** — the source conforms to B grammar.
2. **Statically checked** — the supported B type rules and known constant obligations are satisfied.
3. **Behavior verified** — the implementation satisfies a specific behavioral property. **Not generally available in v0.1.** Runtime assertions and external library signatures do not constitute a proof.

B does not yet guarantee memory safety across foreign boundaries, resource bounds, determinism, side-effect isolation, sandboxing or functional correctness. Imported Python code executes with the user's privileges. Do not run untrusted `.b` files.

## Design decisions

- **Own language, not one more agent prompt.** A B program has a grammar, typed abstract syntax tree and defined behavior.
- **Interoperability by adapters, not guessing.** Every foreign boundary has explicit value conventions and a known or unknown contract.
- **One source of truth.** Grammar in [`b_lang/syntax.lark`](b_lang/syntax.lark); checker/compiler in [`b_lang/compiler.py`](b_lang/compiler.py).
- **Small trusted core.** Only static rules genuinely enforced by the implementation may be advertised as checked.
- **Measure before optimizing syntax.** We will optimize total cost per correct task, not merely character count or token count.

## Documentation

- [B v0.1 language reference](docs/language.md) — syntax, types, evaluation and error rules
- [B 1.0 design proposal](docs/design-b1.md) — proposed richer syntax and formal semantics (not implemented)
- [Architecture](docs/architecture.md) — compiler, runtime, intermediate representation, future backends
- [Foreign-function interfaces](docs/interop.md) — interoperability, type mapping, trust and serialization
- [Verification](docs/verification.md) — which properties are checked, which are not
- [Benchmarks](docs/benchmarks.md) — how to compare B against conventional languages honestly
- [Roadmap](docs/roadmap.md) — implemented versus proposed work

The name **B** is a working name. It is also the name of a historical programming language; this project does not claim to be its continuation.

MIT licensed. See [LICENSE](LICENSE).
