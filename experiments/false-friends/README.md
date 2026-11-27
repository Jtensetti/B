# Study A: False Friends Stopped Before Execution

This preregistered study evaluates **Condition 4**: how many planted cross-ecosystem boundary faults ("false friends") are stopped **before program execution** (at compilation, static checking, or dependency-lock verification) across **B 0.19**, **Typed Python** (`mypy --strict`), **C#** (`dotnet build`, `Nullable=enable`, `TreatWarningsAsErrors=true`), **TypeScript** (`tsc --strict --noEmit`), **Go** (`go vet && go build`), and **Rust** (`rustc -D warnings`).

See [PREREGISTRATION.md](PREREGISTRATION.md) for the frozen protocol, [run_study.py](run_study.py) for the executable benchmark harness, and [results.json](results.json) for full per-case diagnostics and SHA-256 digests.

## Results (25 Planted Boundary Faults + 5 Clean Controls)

| Language | Checker / Gate | Wrong Unit | Wrong Currency | Changed Signature | Silent Behavior Drift | Ecosystem Semantics | Total Stopped | Stop Rate | Control False Positives |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **B 0.19** | `b check --strict --lock` | **5/5** | **5/5** | **5/5** | **5/5** | **5/5** | **25/25** | **100.0%** | **0/5** |
| Typed Python | `mypy --strict` | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 | 5/25 | 20.0% | 0/5 |
| C# (.NET 10) | `dotnet build` | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 | 5/25 | 20.0% | 0/5 |
| TypeScript 5.8 | `tsc --strict --noEmit` | 0/5 | 0/5 | 4/5 | 0/5 | 0/5 | 4/25 | 16.0% | 0/5 |
| Go 1.24 | `go vet && go build` | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 | 5/25 | 20.0% | 0/5 |
| Rust 1.100 | `rustc -D warnings` | 0/5 | 0/5 | 5/5 | 0/5 | 0/5 | 5/25 | 20.0% | 0/5 |

**Condition 4 verdict:** **PASS** — B stops **100.0% (25/25 ≥ 80%)** before execution with **0/5 false positives**, and every individual sibling language stops strictly fewer (best sibling: **20.0%, 5/25**).

## Honest Scope & Limitations

- All 25 faults and 5 clean controls were run against the real compilers/checkers on this host without executing candidate applications.
- Sibling languages *can* catch unit or currency mismatches if a developer manually defines custom wrapper/newtype structs and operators (`struct Km(f64)`, `NewType`, etc.), and can catch silent library drift by writing separate post-install integration test suites. This study compares **idiomatic default static checking and dependency locking** without per-fault custom wrapper frameworks.
- TypeScript stopped 4/5 signature changes because `S5` simulates a real-world JavaScript package changing runtime arity while its ambient `.d.ts` declaration stays stale; B's lock verifier inspects the live npm export directly before execution.

## Reproduce

```sh
python3 experiments/false-friends/run_study.py
```
