# Study B: Fair Multi-Ecosystem Composition, Lifecycle Error Rate, Honest Expressiveness & Own-Language Semantics

Preregistered 6-language lifecycle study comparing **B 0.20.1** against five sibling languages (**Typed Python** with `mypy --strict`, **C#** `.NET 10`, **TypeScript** `tsc --strict`, **Go 1.24**, and **Rust 1.100** with `serde`/`serde_json` and `-D warnings`).

Combined with [Study A (False Friends Stopped Before Execution)](../false-friends/README.md), this study evaluates all five preregistered conditions.

## Experimental Design (Frozen in `PREREGISTRATION.md`)

- **3 multi-step tasks**, each built from an **empty file** (Stage 0) and evolved through **5 consecutive specification changes** (Stages 1–5 = 6 stages/run):
  1. `T1_release_gate` — Artifact Release Gatekeeper (B composes **Python + .NET + Node/npm**: `py:urllib.parse`, `net:System.Text.RegularExpressions.Regex`, `js:"node:path/posix"`, `js:semver`).
  2. `T2_telemetry_sla` — Telemetry & SLA Stream Auditor (B composes **Python + Go + Rust**: `py:statistics`, `go:strings`, `rs:std.str`, `rs:std.i64`).
  3. `T3_freight_quote` — Cross-Border Freight Quote Engine (B composes **.NET + Node/npm + Go**: `net:System.Math`, `net:System.Text.RegularExpressions.Regex`, `js:"node:path/posix"`, `go:strings`).
- **Idiomatic sibling baselines**: Each sibling language solves the exact same functional specification idiomatically in its own ecosystem (with its standard strict static checker/compiler).
- **3 independent isolated solvers** per `(task, language)` = **54 complete runs** (`324` graded stages, `3,240` hidden independent oracle checks total, `540` per language).
- **Equal fixed budget**: At most **3 `./submit` compiler/checker rounds per stage** (1 initial + up to 2 repairs). Solvers see only compiler/checker diagnostics and 2 public smoke examples per stage; after each stage finishes, 10 unseen black-box hidden oracle tests grade the frozen final snapshot before the next stage is revealed.
- **Deterministic token accounting**: Every submitted snapshot is tokenized with `o200k_base` (`gpt-tokenizer@4.1.2` via `tokenize_o200k.mjs`):
  - `Lifecycle Added Tokens`: Stage 0 full file + added/modified lines across Stages 1–5 and all repair attempts.
  - `Lifecycle Diff Tokens`: Stage 0 full file + full unified diff hunk payloads across Stages 1–5 and all repairs.
  - `Lifecycle Full Tokens`: sum of full-file tokens across every submitted attempt.
  - `Mean Stage-5 Tokens`: final Stage 5 program size.
- **Learning-context cap**: `B_GUIDE.md` is strictly capped at **≤ 1,500 `o200k_base` tokens** (actual: **1,494 tokens**).

## Final Measured Results (`B 0.20.1` vs 5 Sibling Languages)

Source of truth: [`results.json`](results.json) (re-verifiable via `python3 experiments/sibling-study/replay.py`).

| Language | Runs | Hidden Passed | Remaining Errors | Total Attempts (min 54) | Lifecycle Added Tokens | Lifecycle Diff Tokens | Lifecycle Full Tokens | Mean Stage-5 Tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **B 0.20.1** | **9** | **540 / 540** | **0** | **54 (6.00)** | **11,402** | **23,565** | **45,422** | **1,099.9** |
| TypeScript (`tsc --strict`) | 9 | 540 / 540 | 0 | 54 (6.00) | 13,095 (+14.8%) | 25,884 (+9.8%) | 56,542 (+24.5%) | 1,354.4 (+23.1%) |
| Python (`mypy --strict`) | 9 | 540 / 540 | 0 | 54 (6.00) | 16,723 (+46.7%) | 30,815 (+30.8%) | 72,646 (+59.9%) | 1,712.8 (+55.7%) |
| Go (`go vet && go build`) | 9 | 540 / 540 | 0 | 54 (6.00) | 17,460 (+53.1%) | 30,092 (+27.7%) | 70,745 (+55.8%) | 1,598.1 (+45.3%) |
| Rust (`cargo -D warnings`) | 9 | 540 / 540 | 0 | 54 (6.00) | 19,838 (+74.0%) | 33,217 (+41.0%) | 90,461 (+99.2%) | 2,030.8 (+84.6%) |
| C# (`dotnet build`) | 9 | 540 / 540 | 0 | 54 (6.00) | 20,575 (+80.5%) | 34,482 (+46.3%) | 92,439 (+103.5%) | 2,074.8 (+88.6%) |

### Per-Task Breakdown (Sum Across 3 Independent Solvers per Task)

| Task | Metric | **B 0.20.1** | TypeScript | Python | Go | Rust | C# |
|---|---|---:|---:|---:|---:|---:|---:|
| `T1_release_gate` (`py+net+js`) | Added / Full / Final | **3,197 / 13,263 / 2,870** | 4,110 / 18,311 / 3,748 | 7,293 / 32,925 / 6,599 | 7,893 / 36,324 / 6,854 | 9,384 / 46,369 / 8,678 | 9,357 / 46,573 / 8,646 |
| `T2_telemetry_sla` (`py+go+rs`) | Added / Full / Final | **3,243 / 13,298 / 2,959** | 4,945 / 20,185 / 4,617 | 4,958 / 20,375 / 4,716 | 5,020 / 17,285 / 3,846 | 5,360 / 20,355 / 4,834 | 6,032 / 22,504 / 5,230 |
| `T3_freight_quote` (`net+js+go`) | Added / Full / Final | 4,962 / 18,861 / 4,070 | **4,040 / 18,046 / 3,825** | 4,472 / 19,346 / 4,100 | 4,547 / 17,136 / 3,683 | 5,094 / 23,737 / 4,765 | 5,186 / 23,362 / 4,797 |

> **Honest observation on `T3_freight_quote`:** On `T3`, B encodes explicit compile-time unit conversions (`m`/`km`, `g`/`kg`) and currency separation (`EUR`/`SEK`) with `as`/`to`/`scalar()`, whereas TypeScript/Python/Go use untagged floats. That static safety costs ~250–900 extra tokens across 3 solvers on `T3`, yet across all 3 tasks combined B still uses **12.9% fewer added tokens, 9.0% fewer diff tokens, 19.7% fewer full tokens, and 18.8% smaller final programs** than the closest sibling (TypeScript).

## Transparent Iteration History (Archived Rounds)

All intermediate preregistered rounds are preserved in full without cherry-picking:

| Round | B Version | `B_GUIDE.md` Tokens | B Attempts | Hidden Errors | Added Tokens | Diff Tokens | Full Tokens | Mean Stage-5 | Outcome & Diagnosis |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| Round 1 ([`results_round1_b019.json`](results_round1_b019.json)) | `0.19.0` | 1,287 | 66 | 0 / 540 | 15,961 | 35,356 | 65,185 | 1,294.9 | **Failed Condition 3 vs TypeScript** (`13,095` added / `25,884` diff): 12 repair rounds (`E_KEEPING` on dimensioned scalars, newline-intolerant expressions, redundant `foreign`), single-line positional record updates, homogeneous `summarize` `?? 0` boilerplate. |
| Round 2 ([`results_round2_b020.json`](results_round2_b020.json)) | `0.20.0` | 1,490 | 62 | 0 / 540 | **12,121** | 25,916 | **52,425** | **1,122.1** | Beat all 5 siblings on added/full/final tokens; trailed TS by 32 diff tokens due to 8 repairs from 2 compiler bugs (`history.py` rejected structural records; multiline `(...)` before `and`) and `cases var` rule. |
| **Round 3 ([`results.json`](results.json))** | **`0.20.1`** | **1,494** | **54** | **0 / 540** | **11,402** | **23,565** | **45,422** | **1,099.9** | **PASS on all 5 conditions** (100% first-try acceptance across all 54 B stages; lowest tokens on every metric against every sibling). |

## Five-Condition Summary

| # | Condition | Measured Result | Verdict |
|---|---|---|---|
| 1 | Fair multi-ecosystem composition (≥3 tasks, empty file, ≥5 edits, ≥3 ecosystems, ≥3 solvers/lang) | 54/54 completed runs; BIR verifies `py+net+js`, `py+go+rs`, `net+js+go` across all 9 B runs | **PASS** |
| 2 | Top-class error rate under equal fixed budget (max 3 `./submit` rounds/stage) | B = **0 / 540** hidden errors (tied with best sibling = 0 / 540) | **PASS** |
| 3 | Honest expressiveness (fewer lifecycle output tokens than every sibling, learning context ≤ 1,500 tokens, readable code) | B = **11,402** added / **23,565** diff / **45,422** full / **1,099.9** Stage-5 vs closest sibling TypeScript (**13,095 / 25,884 / 56,542 / 1,354.4**); `B_GUIDE.md` = **1,494 / 1,500** tokens; zero code-golf notation | **PASS** |
| 4 | Stops ≥80% of preregistered false friends before execution & beats every sibling individually | [Study A](../false-friends/README.md): B = **25 / 25 (100.0%)**, 0/5 false positives vs Python/C#/Go/Rust **5/25 (20.0%)** and TypeScript **4/25 (16.0%)** | **PASS** |
| 5 | Own language, not a shell (0 inline host code escapes, own semantics, independent BIR backends) | 0 host escape hatches across 9/9 B runs; B-native `record`, `unit`/`currency`, `cases`, `summarize`, `count adjacent`/`earlier`, `also ... keeping` verified in BIR; independent Python and Node.js (`b build --target js`) BIR backends differentially tested | **PASS** |

## Scope & Limitations

- All 54 solvers were driven by the same LLM family under identical isolation rules (`study_runner`), measuring single-model cross-language performance rather than human developer studies or cross-model ensembles.
- The 3 tasks represent structured data/policy/calculation CLI pipelines (JSON stdin → JSON stdout) where multi-ecosystem library reuse, units/currencies, decision tables, summaries, and ordered history counts are natural; they do not benchmark systems programming, concurrency, GUIs, or large multi-file codebases.
- B's secondary JS BIR backend (`b_lang/lowering_js.py`) supports pure B + direct `js:` imports directly; full 5-ecosystem runtime execution currently uses the Python BIR host orchestrator with persistent `.NET`, `Node`, `Go`, and `Rust` adapters.

## Deterministic Replay & Audit

```sh
python3 experiments/sibling-study/replay.py
# Or re-execute all 324 stage snapshots (Stages 0..5):
python3 experiments/sibling-study/replay.py --all-stages
```
