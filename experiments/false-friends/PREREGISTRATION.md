# Preregistration: Study A — False Friends Stopped Before Execution

**Frozen before running the study harness.**

## Hypothesis & Decision Criterion (Condition 4)
Out of 25 preregistered planted boundary faults spanning five equal categories (5 each):
1. **Wrong unit (`U1`–`U5`)**: meters vs km, ms vs s, kg vs g, bare float vs km, cross-dimension m→s conversion.
2. **Wrong currency (`C1`–`C5`)**: SEK+EUR addition, USD passed to EUR API, SEK returned as EUR, SEK vs EUR comparison, implicit SEK→EUR conversion.
3. **Changed signature (`S1`–`S5`)**: extra required parameter, return becoming nullable/Option, parameter type Int→Text, removed export, unannotated/external runtime arity drift.
4. **Silently changed library behavior (`B1`–`B5`)**: identical type signature with silently changed rounding mode, semver prerelease matching, tax rate, negative modulo sign, and regex anchor.
5. **Semantic differences between ecosystems (`E1`–`E5`)**: UTF-16 code units vs codepoints, UTF-8 bytes vs codepoints, half-away-from-zero vs half-even rounding, truncated vs floored negative remainder, and JS 53-bit safe integer loss (`9007199254740993`).

Plus **5 clean negative controls** (`CTRL_U`, `CTRL_C`, `CTRL_S`, `CTRL_B`, `CTRL_E`) that contain NO boundary error and MUST be accepted by every tool (testing for false positives).

## Definition of "Stopped Before Execution"
A fault is counted as **stopped before execution** if and only if the language's static compiler, type checker, or dependency lock verifier exits with a non-zero status **without executing the target application**:
- **B**: `b check --strict [--lock FILE.lock.json]`
- **Typed Python**: `mypy --strict`
- **C#**: `dotnet build` (with `<Nullable>enable</Nullable>` and `<TreatWarningsAsErrors>true</TreatWarningsAsErrors>`)
- **TypeScript**: `tsc --strict --noEmit`
- **Go**: `go vet ./... && go build ./...`
- **Rust**: `rustc --crate-type bin -D warnings` (compile/type-check only, binary not executed)

## Idiomatic Representation Fairness Rule
Each sibling language expresses each case using its standard idiomatic library types (`float`/`double`/`number`/`float64`/`f64`, `int`/`long`/`i64`, `str`/`string`/`&str`, and normal dependency imports), without custom hand-built wrapper frameworks invented per fault. B uses its built-in language features (`unit`, `currency`, `expect`, `probe`, `b lock`, `b check --strict --lock`).

## Success Criterion
1. B stops **≥ 80%** (≥ 20/25) of planted boundary faults before execution.
2. **Every individual sibling language** stops strictly fewer than B.
3. B has **0/5 false-positive rejections** on the 5 clean negative controls.
