# Pre-registration: sibling task A, delivery quotes

Committed before any solver runs. Results will be added below the line, whatever they are. Shared rules: [DESIGN.md](../DESIGN.md).

## Task

The [build brief](steps/build.md) and [changes 1–5](steps/): delivery quotes that need all five [libraries](libs/). Tariffs are in Go, road distance in Rust, VAT in C#, Swedish working days in Python, and fuzzy product names come from npm `fastest-levenshtein`. A [B reference build](reference/build.bee) calling all five passes `b check --strict` and grades 0 wrong.

## Solvers

Three Claude Haiku solvers in each of six languages: B, typed Python, TypeScript, Go, Rust and C#. Every workspace holds a copy of `libs/` and `node_modules/`. Each language is run and checked in its usual way:

| Language | Program | Run | Check |
| --- | --- | --- | --- |
| B | `main.bee` | `b run main.bee` | `b check --strict main.bee` |
| Python | `main.py` | `python main.py` | `mypy --strict main.py` |
| TypeScript | `main.ts` | `node main.ts` | `tsc --strict --noEmit --types node main.ts` |
| Go | `go.mod`, `main.go` | `go run .` | `go vet .` |
| Rust | `Cargo.toml`, `src/main.rs` | `cargo run -q --release` | `cargo build` |
| C# | `app/App.csproj` | `dotnet run -c Release --project app/App.csproj` | `dotnet build app` |

The solver runs the whole trial in one agent run and calls the `next` command after each step ([stepper](../next.py)).

## Measures

- **Errors:** 24 hidden orders per step, 6 steps, 144 units per solver, graded by [grade.py](../grade.py) against the [oracle](oracle.py) on each snapshot.
- **Work:** output tokens of each solver's whole run.
- **Oracle errors:** if every solver in every language agrees on a value that differs from the oracle, the oracle is checked by hand against the brief and the library code. A confirmed oracle error is fixed, every snapshot is regraded, and the fix is reported.

This task counts toward conditions 1–3 of the goal together with tasks B and C. No condition is decided by this task alone. Per-language sums of wrong units and output tokens are reported as measured.

---

## Results (added after the run)

All 18 solvers finished the build and all five changes. Data: [`results/results.json`](results/results.json) (per solver and step). Final programs: [`solutions/`](solutions/).

| Language | Wrong units (of 432) | Output tokens | Tokens per solver |
| --- | ---: | ---: | --- |
| TypeScript | 0 | 106 721 | 35 392 · 40 049 · 31 280 |
| C# | 0 | 154 299 | 47 351 · 72 888 · 34 060 |
| Go | 12 | 173 882 | 66 146 · 66 358 · 41 378 |
| Rust | 0 | 212 331 | 95 188 · 64 147 · 52 996 |
| Python | 0 | 288 724 | 185 189 · 54 819 · 48 716 |
| **B** | **0** | **295 531** | 95 991 · 73 238 · 126 302 |

- **Errors:** B 0, equal to the best. Go 2 ran `next` before it had made change 3, so its step-3 program lacked the 400 SEK cap (12 wrong units). Every other program was correct at every step.
- **Work:** B used the most output tokens of the six languages, 2.8 times TypeScript. On this task, condition 3 goes against B.
- **How the others used the libraries:** most ported the four foreign libraries into their own language, read from source, and some cross-checked the ports against the originals. One Python solver and one C# solver called the libraries through bridges they built themselves. Porting 40–120-line libraries was cheap and correct for the models. B's advantage, calling the libraries instead of porting them, did not pay off at this size.
- **B friction seen in the transcripts:** B has no uppercase function, and `b check --strict` could not prove a Float divisor nonzero after a guard, so one solver divided through Python's `operator.truediv`.

### Grading-procedure fixes, made before the results were read as final

1. The stepper skipped every directory named `bin`. One Python solver kept its bridge binaries in `bin/`. The grader restores a root `bin/` from the live workspace. This did not change any score.
2. The first grading run reused cargo's build across steps, because copied sources kept old timestamps. Every Rust snapshot then ran the step-0 binary and scored 78 wrong. The log is kept as [`results/grading-run1-stale-cargo.txt`](results/grading-run1-stale-cargo.txt). The grader now refreshes timestamps, and every language was regraded. The table above is the second run.

Rule violation: solver B 2 wrote test files to `sibA/tests/`, outside its workspace.
