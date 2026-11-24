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
