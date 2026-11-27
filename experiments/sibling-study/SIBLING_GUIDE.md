# Solver Harness Guide

You are solving a 6-stage programming task (Stage 0 from an empty file, followed by Stages 1–5 consecutive changes) in your assigned language.

## Workflow
1. Read `STAGE.md` carefully. It defines the functional specification, JSON stdin/stdout contract, and 2 public examples for the current stage.
2. Edit ONLY your assigned source file (initially empty at Stage 0) cleanly and idiomatically:
   - **B**: `solution.bee` (checked with `b check --strict`, executed with `b run`; must use the 3 ecosystems specified in `STAGE.md`)
   - **Python**: `solution.py` (checked with `mypy --strict`, executed with `python3`)
   - **C#**: `Program.cs` (checked with `dotnet build` with `Nullable=enable` and `TreatWarningsAsErrors=true`, executed with `dotnet run`)
   - **TypeScript**: `solution.ts` (checked with `tsc --strict`, executed with `node`; `semver` is installed in `node_modules`)
   - **Go**: `main.go` (checked with `go vet ./... && go build`, executed as compiled binary)
   - **Rust**: `src/main.rs` (checked with `cargo check` / `cargo build` with `-D warnings`; `serde` with `derive` and `serde_json` are pre-configured in `Cargo.toml`)
3. Run `./submit` in your workspace directory.
   - You have **at most 3 `./submit` attempts per stage** (1 initial + up to 2 repairs).
   - `./submit` runs your language's static compiler/checker and the 2 public examples, and freezes each attempt.
   - Do NOT inspect `./submit` or any files outside your workspace directory.
4. Once `./submit` reports `ACCEPTED (public checks passed)` (or if 3 attempts are used), STOP and report completion so the orchestrator can grade your frozen submission against the hidden oracle and deliver the next stage.
5. Keep code clean, well-typed, and human-readable (no obfuscation or code golf).
