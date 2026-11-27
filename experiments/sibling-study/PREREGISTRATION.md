# Preregistration: Study B — Fair Multi-Ecosystem Composition, Lifecycle Error Rate, Honest Expressiveness & Own-Language Semantics

**Frozen BEFORE dispatching any solver.**

## Frozen Artifact SHA-256 Digests
- `B_GUIDE.md`: `3a7c049e9d72eb9dbdf98029249fb391ff23c0e961f9898eab58786b023c30d2` (**1,287 `o200k_base` tokens**, strictly below the preregistered cap of **1,500 `o200k_base` tokens**)
- `SIBLING_GUIDE.md`: `b5e6176ad9d573eae0998ede736d58ac44a0ffa895fdbca1c87210e0187d6a6e` (469 `o200k_base` tokens)
- `tasks.py` (specs + 180 hidden independent oracle cases): `34b194b143d54b031b5760b24a2a93285f8f76cb8792fcb30a153c2ba1c1a749`
- `harness.py`: `c935b777668eb00af7c50c59485124fbe9363769ce7b5b4c7aa4a54d0302eb7f`
- `tokenize_o200k.mjs` (`gpt-tokenizer@4.1.2`, `o200k_base`): `4ee7698ed4a2c5d1bd76b8802ea138ce3e4af96565c2a13c2c2c938db9c3e377`

## Experimental Design (Conditions 1, 2, 3, and 5)
- **Tasks (3)**:
  1. `T1_release_gate` — Artifact Release Gatekeeper (B composes **Python + .NET + Node/npm**)
  2. `T2_telemetry_sla` — Telemetry & SLA Stream Auditor (B composes **Python + Go + Rust**)
  3. `T3_freight_quote` — Cross-Border Freight Quote Engine (B composes **.NET + Node/npm + Go**)
- **Languages (6)**: `B` (`b check --strict`), `Python` (`mypy --strict`), `C#` (`dotnet build`, `Nullable=enable`, `TreatWarningsAsErrors=true`), `TypeScript` (`tsc --strict`), `Go` (`go vet && go build`), `Rust` (`cargo build` with `RUSTFLAGS="-D warnings"`, `serde` + `serde_json`).
  - Each sibling language solves the exact same functional specification **idiomatically in its own ecosystem**.
- **Independent Solvers**: **3 fresh, isolated solver contexts** per `(task, language)` -> `3 × 3 × 6 = 54` complete independent runs.
- **Lifecycle**: Every run starts from an **empty file** (Stage 0) and progresses sequentially through **5 consecutive changes** (Stages 1–5), totaling **6 stages per run** (`324` total graded stages; `3,240` hidden black-box oracle evaluations across all 54 runs, `540` per language).
- **Equal Fixed Budget (Condition 2)**: At most **3 `./submit` compiler/checker rounds per stage** (1 initial + up to 2 repairs), identical for all 6 languages. Solvers see ONLY static checker output and 2 public smoke examples per stage. After each stage finishes, the frozen hidden independent oracle (10 unseen test cases per stage) grades the frozen final submission before the next stage's requirements are revealed.
- **Honest Expressiveness & Output Tokens (Condition 3)**:
  - Measured deterministically with `o200k_base` (`gpt-tokenizer@4.1.2`) across the full lifecycle (Stage 0 + Stages 1–5 + all repair attempts):
    1. `total_lifecycle_added_tokens`: Stage 0 full file + added/modified code lines on every edit & repair attempt across all 6 stages.
    2. `total_lifecycle_diff_tokens`: Stage 0 full file + full unified diff hunk payloads across all 6 stages & repairs.
    3. `total_lifecycle_full_tokens`: sum of full-file tokens across every submitted attempt.
    4. `mean_final_stage5_tokens`: final Stage 5 program size.
  - Preregistered cap on B learning context (`B_GUIDE.md`): **≤ 1,500 `o200k_base` tokens** (actual: **1,287 tokens**). No unreadable code-golf notation.
- **Own Language, Not a Shell (Condition 5)**:
  - Automated check rejects any raw embedded host code escape hatches (`eval`, `exec`, `subprocess`, etc.) and verifies via BIR that all 3 required ecosystems are genuinely invoked while business logic, units/currencies, records, decision tables, summaries, and history counts are expressed natively in B.

## Success Criteria
- **Condition 1**: All 3 tasks × 6 languages × 3 independent solvers complete Stage 0 (from empty file) + 5 consecutive changes; every B program composes ≥ 3 ecosystems (`py+net+js`, `py+go+rs`, `net+js+go`).
- **Condition 2**: Under the fixed 3-round/stage budget, B's total remaining hidden-oracle errors across all 9 B runs (540 hidden checks) is **≤** the best of the 5 sibling languages individually.
- **Condition 3**: B uses **fewer total lifecycle output tokens** (including Stage 0 + 5 edits + all repairs) than **every single one** of Typed Python, C#, TypeScript, Go, and Rust, under the 1,500-token `B_GUIDE.md` cap.
- **Condition 5**: 0 raw embedded host code escape hatches, all logic expressed in B's own semantics, verified across 2 independent BIR backends (`py` + `js`).

---

## Round 2 Preregistration (B 0.20.0) — Frozen BEFORE Dispatching B 0.20.0 Solvers

Round 1 (`B 0.19.0`, archived in `results_round1_b019.json`) passed Conditions 1, 2 (0/540 errors), 4 (25/25 = 100%), and 5, and achieved the smallest final Stage 5 program size (`1,294.9` vs TypeScript `1,354.4`), **but failed Condition 3** against TypeScript (`15,961` vs `13,095` added tokens; `35,356` vs `25,884` diff tokens; `65,185` vs `56,542` full tokens) due to 12 extra repair rounds (`E_KEEPING` on dimensioned scalars, newline-intolerant expressions, redundant `foreign` declarations) and forced single-line positional record updates + homogeneous `summarize` boilerplate.

B `0.20.0` addresses these general-purpose language ergonomics cleanly (structural `record { ... }` literals, named multiline record construction, heterogeneous typed `summarize` with direct `.field` access and filtered `min`/`max`, inferred non-recursive `fn` return types, multiline expressions, and dimensioned scalars in `also ... keeping`).

### Round 2 Frozen Artifact SHA-256 Digests
- `B_GUIDE.md` (v0.20): `f7ac99debfa6021eea4eccfd37fbb314bd2213e423849f0f1bac905a329ae4a9` (**1,490 `o200k_base` tokens**, strictly below the preregistered 1,500-token cap)
- `SIBLING_GUIDE.md`: **UNCHANGED** (`b5e6176ad9d573eae0998ede736d58ac44a0ffa895fdbca1c87210e0187d6a6e`)
- `tasks.py`: **UNCHANGED** (`34b194b143d54b031b5760b24a2a93285f8f76cb8792fcb30a153c2ba1c1a749`)
- `harness.py`: **UNCHANGED** (`c935b777668eb00af7c50c59485124fbe9363769ce7b5b4c7aa4a54d0302eb7f`)
- `tokenize_o200k.mjs`: **UNCHANGED** (`4ee7698ed4a2c5d1bd76b8802ea138ce3e4af96565c2a13c2c2c938db9c3e377`)

Because `tasks.py`, `SIBLING_GUIDE.md`, `harness.py`, and `tokenize_o200k.mjs` are byte-for-byte identical, the 45 completed sibling-language runs (Python, C#, TypeScript, Go, Rust) remain untouched, while all 9 B runs (3 tasks × 3 fresh independent solvers from empty files) are re-run cleanly on B `0.20.0`.

---

## Round 3 Preregistration (B 0.20.1) — Frozen BEFORE Dispatching B 0.20.1 Solvers

Round 2 (`B 0.20.0`, archived in `results_round2_b020.json`) beat **all 5 sibling languages** on `total_lifecycle_added_tokens` (`12,121` vs TypeScript `13,095`), `total_lifecycle_full_tokens` (`52,425` vs `56,542`), and `mean_final_stage5_tokens` (`1,122.1` vs `1,354.4`) with `0/540` errors, while trailing TypeScript by 32 tokens (`25,916` vs `25,884`) on `total_lifecycle_diff_tokens` solely due to 8 repair rounds caused by 2 compiler bugs introduced/missed in `0.20.0` (structural `Record` rejected by `history.py`; newlines inside `(...)`/`[...]` not ignored before `and`/`or`) and `cases var` syntax not noting the variable-pivot rule in `B_GUIDE.md`.

B `0.20.1` fixes both compiler bugs (`history.py` structural record support; implicit newline continuation inside `(...)`/`[...]`) and clarifies `cases var` in `B_GUIDE.md`.

### Round 3 Frozen Artifact SHA-256 Digests
- `B_GUIDE.md` (v0.20.1): `66c7a5438cb9a073435623f4783d40e9e91ef2aa9ef138f353448e5326573598` (**1,494 `o200k_base` tokens**, strictly below the preregistered 1,500-token cap)
- `SIBLING_GUIDE.md`: **UNCHANGED** (`b5e6176ad9d573eae0998ede736d58ac44a0ffa895fdbca1c87210e0187d6a6e`)
- `tasks.py`: **UNCHANGED** (`34b194b143d54b031b5760b24a2a93285f8f76cb8792fcb30a153c2ba1c1a749`)
- `harness.py`: **UNCHANGED** (`c935b777668eb00af7c50c59485124fbe9363769ce7b5b4c7aa4a54d0302eb7f`)
- `tokenize_o200k.mjs`: **UNCHANGED** (`4ee7698ed4a2c5d1bd76b8802ea138ce3e4af96565c2a13c2c2c938db9c3e377`)

All 9 B runs (3 tasks × 3 fresh independent solvers from empty files) are re-run cleanly on B `0.20.1` against the untouched 45 sibling-language runs.


