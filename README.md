# B

**B is an experimental programming language designed for programs written by AI.** A model can express a calculation in typed B source, reuse existing Python, .NET and Node.js libraries, and let the compiler check and execute the result. The research goal is working software in fewer attempts at lower total cost.

**Version 0.16 (research prototype).** Preferred source suffix: `.bee`; `.b4`, `.bsrc` and `.b` are supported aliases. B is unrelated to the historical Bell Labs B language.

> **Safety and maturity:** B is not a sandbox, a general-purpose native compiler, a proof assistant or a complete Python/.NET type checker. `b check --strict` only accepts programs without *known static warnings in the supported subset*. Import signatures are assumptions, not proofs. Executing B can run arbitrary installed Python code.

## Compute several results in one traversal

```bee
fn audit(ms: List[Int], floor: Int) -> Dict[Text,Int] pure = summarize t in ms {
    cues: count
    short: count where t < floor
    missing_ms: sum (floor - t) where t < floor
}
let report = audit([1000, 480, 550], 550)
print report["missing_ms"] ?? 0
```

This prints `70`. B compiles the three fields into one loop. The function chooses which measurements matter. The compiler supplies the counters, initial values, and iteration order. A [runnable subtitle-duration audit](examples/cue-duration-audit.bee) reads a JSON array on standard input. The [collection experiment](experiments/collection-reductions/README.md) compares a five-field report with Python built-ins and a hand-written loop, including the cost of validation at the function boundary.

## Apply a small change from a compact row

```sh
cp examples/registers/dispatch.bee dispatch-work.bee
printf 'route 5 "express"\n' | b next dispatch-work.bee --from-short -
printf 'route 5 "express"\n' | b next dispatch-work.bee --from-short - --apply
```

The first command after copying displays `next route when days == 5 => "express"`. The second applies it. B recovers `days` because the target has exactly one parameter. For a function with several parameters the row includes the chosen name. Use an ordinary `next` condition for an interval or a combination of parameters. [Syntax and limits](docs/handoffs.md#compact-input) · [Comparison with ordinary B](experiments/shorthand-pilot/README.md).

## Leave the next edit in the program

```bee
fn route(days: Int) -> Text pure = if days < 3 then "priority" else "standard"
next route when days == 5 => "express"
```

This program still returns `"standard"` for day 5. `b next FILE` prints the pending instruction. Add `--context` to see the target function alongside it. `b next FILE --apply` checks it, adds the exception to the function and removes the instruction. The next run returns `"express"`. Both forms are B code with the usual types, contracts and effects. [Handoffs and upgrading old source](docs/handoffs.md).

## Edit a decision as a table

```bee
fn route(days: Int) -> Text pure = cases days {
    < 0 => "overdue"
    == 0 => "today"
    <= 3 => "priority"
    else => "standard"
}
```

`b view examples/registers/dispatch.bee --function route --register ordinary` displays the same function as nested `if` expressions. B checks that the full program has identical typed BIR before emitting the declaration. You can mix tables and formulas in one function. [Syntax, examples and limits](docs/registers.md) · [AI editing pilot](experiments/register-pilot/README.md).

## Use an existing npm function

```bee
use js:semver as versions
let chosen: Option[Text] = versions.maxSatisfying(["0.2.9", "0.2.10", "0.3.0"], "^0.2.0")
print chosen ?? "no compatible release"
```

B knows the signature of this semver 7 function. With Node and the package installed it prints `0.2.10`. Other packages can expose synchronous named exports through a typed declaration. The [examples](experiments/node-interop/README.md) include release selection, spelling suggestions and a program that passes values through three runtimes.

```sh
npm ci --prefix experiments/node-interop --ignore-scripts --no-audit --no-fund
b run experiments/node-interop/release.bee
b run experiments/node-interop/spelling.bee
```

## Catch a bad interaction in one check

`b check examples/intent/compact.bee --joint examples/intent/uniform.json` shows two individually legal rows that cannot share a screen under a uniform style. One command can check several relationships and give a concrete failing pair for each. In two maintenance tasks all eight AI submissions passed the independent oracle on the first try, four with B feedback and four with typed Python property feedback. [Joint checks](docs/joint-checks.md) · [Independent AI editing pilot](experiments/first-pass/README.md).

## Ask which requirement matters to an edit

A layout function returns gap 1 at rank 0. A proposed change returns 2 there. Several product requirements fit the original program. B can ask whether that one alternative is permitted, then decide the change on a finite input grid while leaving unrelated requirements open.

```sh
b clarify examples/intent/layout.bee examples/intent/layout.json --edit examples/intent/compact.bee
b clarify examples/intent/layout.bee examples/intent/layout.json --edit examples/intent/compact.bee \
  --answer '{"inputs":{"rank":0},"result":2,"allowed":true}' --json
```

In a matched two-product experiment, B, typed Python and fixed plain-language questions reached the same 48 correct edit decisions when the owner's rule was listed. Each active approach made eight mistakes across twelve decisions when the true rule was missing. [Command and limits](docs/contract-questions.md) · [Methods and results](experiments/intent-pilot/README.md).

## Ask B what a function does

`b discover` uses a finite set of candidate contracts and chooses inputs that separate competing rules. A second analysis can prove a surviving integer equality symbolically. Supply an independent expectation to check it against the same code.

```sh
b discover examples/conservation.bee --function accounted --expect 'result == free + booked' --json
b check examples/conservation-modular.bee --strict --require-proofs
```

The first command finds that a reservation preserves the total, checks the two helper bodies and reports both dependencies. The second checks a version whose helpers publish their exact changes. Callers can then rely on the declared conservation law.

In an eight-run AI pilot, all four solvers with discovery and all four without it met the same product requirements. Discovery added a compiler call per run. On one starter, copying a proved formula into the interface would exclude 34 of 41 allowed alternatives. [Command and proof limits](docs/contract-discovery.md) · [Tasks, submissions and independent scoring](experiments/contract-pilot/README.md).

## When a result depends on the input

In B 0.9 a producer can publish a checked rule such as “after tick three, velocity is negative.” A caller in that time range can prove that descent speed is positive. A second caller can safely use it as a divisor. A variant in which the body rebounds at tick five loses all three proofs.

```sh
b check examples/mechanics/flight.bee --strict --require-proofs
b impact examples/mechanics/flight.bee examples/mechanics/rebound.bee
```

On a sequencer maintenance task, six AI submissions passed all 102 behavior checks. The initial difference in checker calls disappeared when a new group learned its configuration upfront. See [conditional guarantees, examples and limits](docs/conditional-guarantees.md), the [AI maintenance experiment](experiments/law-pilot/README.md) and the [cross-language operator probe](experiments/operator-correspondence/README.md).

## What happens when a contract changes?

A provider used to promise a positive count. Its new contract permits zero. B 0.8 can follow that change into two callers. Adding a reserve of ten still produces at least ten. Dividing a cost by the count loses its guarantee that the denominator is nonzero.

```sh
b impact examples/revisions/count-positive.bee examples/revisions/count-zero.bee
b check examples/revisions/count-positive.bee --strict --require-proofs --json
b check examples/revisions/count-zero.bee --require-proofs --json  # exits 1
```

The report identifies the function, expression site, requirement, proof status and direct dependencies. Native B functions can use independently established integer contracts across calls. The analysis distinguishes a lost guarantee from a demonstrated runtime failure. See [contract analysis and revision comparison](docs/composition.md).

In a [single-task AI maintenance pilot](experiments/change-pilot/README.md), B 0.7, B 0.8 and typed Python each passed the same 110 behavior checks. A separate partial edit passed all four public examples while breaking two callers. B 0.8 identified both lost proofs. Total token and inference costs were unmeasured.

## Checked Python source adoption (0.7)

B can now compile a **small, explicitly restricted subset of Python source into native B functions**, rather than importing an entire Python module at runtime:

```bee
permit [console]
adopt py:b_examples.pure_kernels.square as sq
fn triple_square(x: Float) -> Float pure = sq(x) * 3.0
print triple_square(4.0)
```

The `adopt` directive reads a top-level Python function, translates allowed expression-only code into BIR, type-checks and emits a native B function. **The original Python module is not imported or executed** by that compiled function. Unsupported Python code is rejected (`E_ADOPT`), not silently interpreted. BIR records the source file SHA-256. Inspect candidates with `b adopt-audit py:MODULE --json`.

**Measured limitation:** the first narrow experiment adopted 5/9 functions in our controlled example but **0/20** in Python's real `statistics` module and **0/5** in `textwrap`. This is *not* general library integration or mathematical verification. See [the scope, results and limitations](docs/source-adoption.md).

## Contracts and effects (introduced in B 0.6)

**Effect budgets and function contracts are native B syntax**, checked before the Python backend executes. B can now prove a narrow family of integer postconditions, reject certain broken preconditions and effects, and enforce other contracts at runtime:

```bee
permit [console]
fn successor(x: Int) -> Int pure requires x >= 0 ensures result > 0 = x + 1
print successor(41)
```

`pure` forbids unknown foreign effects inside a B function. `permit [...]` tracks a small set of program effects (`console` and `foreign`), **not actual OS capabilities**. BIR records whether a postcondition is proved using integer intervals or only checked at runtime. An imported function's type does not prove its behavior. See [the contract and effect specification](docs/contracts-effects.md).

## BIR pipeline

A real, **typed backend-neutral intermediate representation (BIR)** sits between B source and the executable backend:

```text
  .bee source
      |
  B parser + B checker + type/provenance catalog
      |
  BIR v2: types, contracts, effect classifications, source provenance
      |
  conservative pure-operation optimization
      |
  Python AST backend --> CPython / real Python packages
                        --> explicit typed .NET bridge
                        --> Node worker for synchronous JavaScript exports
```

The Python backend **consumes BIR**, not the source language's syntax tree. BIR is JSON-inspectable; it can preserve a referenced Python, .NET or JavaScript function's assumed signature, backend and provenance. This makes another backend possible in principle, but **only the Python lowering backend is implemented**.

BIR optimization folds supported pure literals without evaluating foreign functions or removing runtime type guards.

## A B program

```text
use py:statistics as stats
use net:System.Math as Math

fn square(x: Float) -> Float = x * x
let values = [3.0, 4.0, 5.0]
let avg: Float = stats.mean(values)
let result: Float = Math.Sqrt(square(avg) + 9.0)
print result
```

This is B source, not a Python program. The `statistics.mean` function runs in CPython and `System.Math.Sqrt` through the explicit .NET host. Both calls appear in the **same** BIR vocabulary with distinct foreign backend tags.

## Install and run

Requires Python 3.11+. The .NET example requires the .NET 10 SDK. The JavaScript examples use Node.js (CI uses Node 22) and any packages imported by the program.

```sh
python -m pip install -e '.[dev]'
b check examples/adopt.bee --strict
b run examples/adopt.bee
b adopt-audit py:statistics --json
b check examples/contracts.bee --strict --json
b run examples/contracts.bee
b check examples/effects.bee --strict
b run examples/effects.bee
b check examples/polyglot.bee --strict
b run examples/polyglot.bee
b ir examples/polyglot.bee --strict           # checked BIR as JSON
b ir examples/polyglot.bee --optimized        # BIR after pure literal folding
b build examples/polyglot.bee                 # show emitted Python backend code
b inspect py:b_examples.poly_lib --json      # static signatures
b audit py:b_examples.demo_lib --json        # coverage: direct functions only
pytest -q
```

To measure coverage of installed real packages (no installation is performed):

```sh
python -m scripts.audit_libraries > audit.json
b audit py:numpy --json
b run examples/numpy_unchecked.bee  # requires NumPy; dynamic, not strict-safe
```

## The important negative result

Our local audit on **21 November 2026** found that B 0.5 could statically understand **0 of 1 directly declared functions** in NumPy's root stub, which also contains hundreds of named re-exports. In the submodule `numpy._core.fromnumeric`, B could parse **0 of 41** direct public function declarations. This **does not mean NumPy has one function, or that zero NumPy functions can be executed by B**: it means our intentionally restricted signature reader cannot yet interpret its complex API definitions. See [the measured audit](docs/library-audit.md), [raw observation](docs/coverage-observed-2026-11-21.json) and [coverage tool](b_lang/audit.py).

This limitation matters more than adding new punctuation or another file extension. Next steps must tackle public re-exports, object/array types, generics, keyword arguments and verified conversions.

## Implemented boundaries

| Layer | Working today | Not yet provided |
| --- | --- | --- |
| B language | Own grammar, immutable names, typed functions, conditions, ordered decision tables, named list reductions, optional dictionary lookups, `??`, `pure`, `requires`, `ensures`, `permit`, `adopt` | General loops, records, pattern matching, user generics |
| BIR v2 | Typed semantic nodes, function contracts, effect inventory, foreign catalog, JSON view, pure constant optimization | Independently verified IR loading, source maps, multi-target lowering |
| Python libraries | Actual import/call, limited annotation discovery, overloads, dynamic fallback and narrow source adoption | Full typeshed, re-export tracking, package-version locking |
| Node.js libraries | Typed POSIX path and semver functions, plus explicit declarations for synchronous named npm exports | Automatic TypeScript signature discovery, promises, callbacks and object handles |
| .NET libraries | Restricted `System.Math` and `Regex` host, metadata verified in CI | Arbitrary assemblies, object models, reflection-based adapters |
| Correctness | Static types/errors, integer bounds, conditional guarantees, affine equalities, revision comparison, runtime contracts and conservative effect classification | General proof system, fine-grained external effects, sandboxing |
| AI advantage | Explicit machine-readable IR and diagnostics | Any measured improvement in AI's correctness or tokens |

## Project references

- [Contract questions about proposed edits (0.11)](docs/contract-questions.md)
- [Discovering and checking contracts (0.10)](docs/contract-discovery.md)
- [Contract analysis and revision comparison (0.8)](docs/composition.md)
- [Language and grammar](docs/language.md)
- [Source adoption (0.7): rules, measured limits and BIR provenance](docs/source-adoption.md)
- [Contracts, interval proofs and effects (0.6)](docs/contracts-effects.md)
- [BIR semantics and implementation](docs/bir.md)
- [Cross-language library bridges](docs/interop.md)
- [Real-library audit](docs/library-audit.md)
- [Experimental evidence](docs/experiments.md)
- [Architectural decisions](docs/architecture.md)
- [Research directions beyond interoperability](docs/research-directions.md)
- [Roadmap](docs/roadmap.md)

**Status:** the code is a research prototype, with tests on the implemented subset. An independent AI building and modifying a substantial B application has **not** yet been evaluated.

MIT licensed.
