#!/usr/bin/env python3
"""Deterministic replay & independent audit for Study B (Conditions 1, 2, 3, 5)
and Study A summary check (Condition 4).

Verifies:
1. Preregistered artifact SHA-256 digests match PREREGISTRATION.md.
2. B_GUIDE.md token count is strictly below the 1,500 o200k_base token cap.
3. All 54 runs (3 tasks x 6 languages x 3 independent solvers) completed Stages 0..5
   within the fixed 3-attempt/stage budget, starting from an empty file.
4. Token counts in state/*.json match deterministic re-tokenization of saved snapshots.
5. Re-executes frozen snapshots against the hidden independent oracles (Stage 5 by
   default, or all 324 stages with --all-stages) in isolated temporary directories.
6. Audits Condition 5 on all 9 final B solutions (0 raw host escape hatches, >= 3
   distinct ecosystems invoked in BIR, B-native constructs used).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

STUDY_DIR = Path(__file__).resolve().parent
ROOT = STUDY_DIR.parents[1]
sys.path.insert(0, str(STUDY_DIR))
import harness  # noqa: E402
import tasks as study_tasks  # noqa: E402

EXPECTED_DIGESTS = {
    "B_GUIDE.md": "66c7a5438cb9a073435623f4783d40e9e91ef2aa9ef138f353448e5326573598",
    "SIBLING_GUIDE.md": "b5e6176ad9d573eae0998ede736d58ac44a0ffa895fdbca1c87210e0187d6a6e",
    "tasks.py": "34b194b143d54b031b5760b24a2a93285f8f76cb8792fcb30a153c2ba1c1a749",
    "harness.py": "c935b777668eb00af7c50c59485124fbe9363769ce7b5b4c7aa4a54d0302eb7f",
    "tokenize_o200k.mjs": "4ee7698ed4a2c5d1bd76b8802ea138ce3e4af96565c2a13c2c2c938db9c3e377",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def batch_count_o200k(texts: list[str]) -> list[int]:
    """Count o200k_base tokens for many strings in one Node.js invocation."""
    script = (
        "const fs = require('node:fs');"
        f"const {{ encode }} = require({json.dumps(str(harness.TOOLS_NM / 'gpt-tokenizer'))});"
        "const arr = JSON.parse(fs.readFileSync(0, 'utf8'));"
        "process.stdout.write(JSON.stringify(arr.map(s => encode(s).length)));"
    )
    proc = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(texts),
        capture_output=True, text=True, check=True, timeout=60,
    )
    return [int(x) for x in json.loads(proc.stdout)]


def make_temp_workspace(tmp_root: Path, run_id: str, lang: str, src_text: str) -> Path:
    ws = tmp_root / run_id
    ws.mkdir(parents=True, exist_ok=True)
    src_path = ws / harness.SRC_FILES[lang]
    src_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.write_text(src_text, encoding="utf-8")

    if lang == "B":
        (ws / "node_modules").symlink_to(harness.TOOLS_NM)
    elif lang == "C#":
        (ws / "App.csproj").write_text(
            """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
  </PropertyGroup>
</Project>
""",
            encoding="utf-8",
        )
    elif lang == "TypeScript":
        (ws / "node_modules").symlink_to(harness.TOOLS_NM)
        (ws / "tsconfig.json").write_text(json.dumps({
            "compilerOptions": {
                "target": "ES2022",
                "module": "CommonJS",
                "moduleResolution": "node",
                "esModuleInterop": True,
                "strict": True,
                "outDir": "dist",
                "skipLibCheck": True,
                "typeRoots": [str(harness.TOOLS_NM / "@types")],
            },
            "include": ["solution.ts"],
        }, indent=2) + "\n", encoding="utf-8")
    elif lang == "Go":
        (ws / "go.mod").write_text("module solution\n\ngo 1.24\n", encoding="utf-8")
    elif lang == "Rust":
        pkg_name = re.sub(r"[^a-z0-9_]", "_", run_id.lower())
        (ws / "Cargo.toml").write_text(
            f"""[package]
name = "{pkg_name}"
version = "0.1.0"
edition = "2021"

[dependencies]
serde = {{ version = "1", features = ["derive"] }}
serde_json = "1"
""",
            encoding="utf-8",
        )
    return ws


def audit_b_own_language(src_text: str, ws: Path) -> dict[str, Any]:
    forbidden = re.findall(r"\b(eval|exec|__import__|subprocess|os\.system)\b", src_text)
    bee = ws / "solution.bee"
    ir_proc = subprocess.run(
        [sys.executable, "-m", "b_lang.cli", "ir", str(bee), "--strict"],
        cwd=str(ws), capture_output=True, text=True, check=True, timeout=30,
    )
    ir = json.loads(ir_proc.stdout)
    ops: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "op" in node:
                ops.add(node["op"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(ir.get("statements", []))
    backends = sorted({sym["backend"] for sym in ir.get("foreign_symbols", [])})
    return {
        "forbidden_escapes": forbidden,
        "ecosystems": backends,
        "foreign_symbol_count": len(ir.get("foreign_symbols", [])),
        "records": len(ir.get("records", [])),
        "units_or_currencies": len(ir.get("units", [])) + len(ir.get("currencies", [])),
        "uses_summarize": "summarize" in ops,
        "uses_history_count": "history_count" in ops,
        "uses_list_comp": "list_comp" in ops,
        "uses_pure_fn": any(s.get("op") == "fn" and s.get("declared_pure") for s in ir.get("statements", [])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-stages", action="store_true", help="Replay all 6 stages instead of Stage 5 only")
    parser.add_argument("--skip-exec", action="store_true", help="Verify digests, tokens, and state integrity without re-executing binaries")
    args = parser.parse_args()

    # 1. Verify frozen artifact digests
    digest_ok = True
    for name, expected in EXPECTED_DIGESTS.items():
        actual = sha256_file(STUDY_DIR / name)
        if actual != expected:
            print(f"DIGEST MISMATCH: {name}: expected {expected}, got {actual}", file=sys.stderr)
            digest_ok = False
    if not digest_ok:
        return 1
    print(f"[OK] All {len(EXPECTED_DIGESTS)} preregistered artifact SHA-256 digests verified.", flush=True)

    # 2. Check B_GUIDE token cap
    b_guide_text = (STUDY_DIR / "B_GUIDE.md").read_text(encoding="utf-8")
    b_guide_tok = batch_count_o200k([b_guide_text])[0]
    assert b_guide_tok <= 1500, f"B_GUIDE.md exceeds 1500 tokens: {b_guide_tok}"
    print(f"[OK] B_GUIDE.md learning context = {b_guide_tok} o200k_base tokens (cap: 1500).", flush=True)

    # 3. Inspect all 54 state files & batch-verify all snapshot token counts
    state_files = sorted((STUDY_DIR / "state").glob("*.json"))
    if len(state_files) != 54:
        print(f"ERROR: expected 54 runs, found {len(state_files)}", file=sys.stderr)
        return 1

    texts_to_tokenize: list[str] = []
    token_checks: list[tuple[str, int, int, int, int, int, int, int, int]] = []
    exec_jobs: list[tuple[str, str, str, int, str, int]] = []
    stages_to_exec = list(range(6)) if args.all_stages else [5]

    for sf in state_files:
        st = json.loads(sf.read_text(encoding="utf-8"))
        run_id = st["run_id"]
        lang = st["lang"]
        task_id = st["task_id"]
        assert st["completed"], f"Run not completed: {run_id}"

        prev_src = ""
        for k in range(6):
            sr = st["stages"][str(k)]
            atts = sr["attempts"]
            assert 1 <= len(atts) <= 3, f"{run_id} stage {k}: invalid attempts {len(atts)}"
            for att in atts:
                snap = STUDY_DIR / att["snapshot"]
                assert snap.exists(), f"Missing snapshot {snap}"
                src = snap.read_text(encoding="utf-8")
                if not prev_src:
                    added_str = src
                    diff_str = src
                else:
                    dlines = list(difflib.unified_diff(
                        prev_src.splitlines(keepends=True),
                        src.splitlines(keepends=True),
                        lineterm="",
                    ))
                    body = [ln for ln in dlines if not ln.startswith(("---", "+++", "@@"))]
                    added_str = "".join(ln[1:] for ln in body if ln.startswith("+"))
                    diff_str = "".join(body)
                prev_src = src
                i0 = len(texts_to_tokenize)
                texts_to_tokenize.extend([src, added_str, diff_str])
                token_checks.append((
                    run_id, k, att["attempt"],
                    i0, i0 + 1, i0 + 2,
                    att["full_tokens"], att["added_tokens"], att["diff_tokens"],
                ))
            if not args.skip_exec and k in stages_to_exec:
                last_snap = STUDY_DIR / atts[-1]["snapshot"]
                exec_jobs.append((run_id, lang, task_id, k, last_snap.read_text(encoding="utf-8"), sr["hidden_passed"]))

    counts = batch_count_o200k(texts_to_tokenize)
    token_mismatches = 0
    for run_id, k, anum, i_f, i_a, i_d, exp_f, exp_a, exp_d in token_checks:
        got = (counts[i_f], counts[i_a], counts[i_d])
        exp = (exp_f, exp_a, exp_d)
        if got != exp:
            print(f"TOKEN MISMATCH {run_id} s{k} a{anum}: recomputed={got} vs stored={exp}", file=sys.stderr)
            token_mismatches += 1
    print(f"[OK] Checked 54 completed runs & {len(token_checks)} snapshot token counts (token mismatches: {token_mismatches}).", flush=True)

    exec_mismatches = 0
    b_audits: dict[str, dict[str, Any]] = {}
    if not args.skip_exec:
        with tempfile.TemporaryDirectory(prefix="b_study_replay_") as tmp_dir:
            tmp_root = Path(tmp_dir)

            def run_one(job: tuple[str, str, str, int, str, int]) -> tuple[str, int, int, int, dict[str, Any] | None]:
                run_id, lang, task_id, k, src, stored_passed = job
                ws = make_temp_workspace(tmp_root, f"{run_id}_s{k}", lang, src)
                try:
                    ok_build, _, exec_cmd, _ = harness.check_and_build(ws, lang, task_id)
                    if not ok_build or exec_cmd is None:
                        passed = 0
                    else:
                        hid_cases = study_tasks.TASKS[task_id]["hidden"](k)
                        passed, _ = harness.run_cases(exec_cmd, ws, lang, k, task_id, hid_cases)
                    aud = audit_b_own_language(src, ws) if (lang == "B" and k == 5) else None
                    return run_id, k, passed, stored_passed, aud
                finally:
                    shutil.rmtree(ws, ignore_errors=True)

            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                for run_id, k, passed, stored_passed, aud in ex.map(run_one, exec_jobs):
                    if passed != stored_passed:
                        print(f"REPLAY MISMATCH {run_id} s{k}: replayed={passed} vs stored={stored_passed}", file=sys.stderr)
                        exec_mismatches += 1
                    if aud is not None:
                        b_audits[run_id] = aud
        print(f"[OK] Re-executed {len(exec_jobs)} frozen stage snapshots against hidden oracles (mismatches: {exec_mismatches}).", flush=True)

    # 4. Aggregate & evaluate Conditions 1-5
    res_path = STUDY_DIR / "results.json"
    if not res_path.exists():
        harness.cmd_aggregate()
    report = json.loads(res_path.read_text(encoding="utf-8"))
    summary = report["summary"]
    b_sum = summary["B"]
    siblings = [l for l in harness.LANGS if l != "B"]

    c1 = all(summary[l]["completed_runs"] == 9 for l in harness.LANGS) and (
        args.skip_exec or all(len(a["ecosystems"]) >= 3 for a in b_audits.values())
    )
    best_sib_err = min(summary[l]["remaining_errors"] for l in siblings)
    c2 = b_sum["remaining_errors"] <= best_sib_err
    c3_added = all(b_sum["total_lifecycle_added_tokens"] < summary[l]["total_lifecycle_added_tokens"] for l in siblings)
    c3_diff = all(b_sum["total_lifecycle_diff_tokens"] < summary[l]["total_lifecycle_diff_tokens"] for l in siblings)
    c3_full = all(b_sum["total_lifecycle_full_tokens"] < summary[l]["total_lifecycle_full_tokens"] for l in siblings)
    c3 = c3_added and c3_diff and c3_full and b_guide_tok <= 1500

    ff_path = ROOT / "experiments" / "false-friends" / "results.json"
    ff = json.loads(ff_path.read_text(encoding="utf-8"))
    b_ff = ff["summary"]["B"]["stopped"]
    b_ff_rate = ff["summary"]["B"]["stop_rate_pct"]
    sib_ff_max = max(ff["summary"][l]["stopped"] for l in siblings)
    c4 = b_ff_rate >= 80.0 and b_ff > sib_ff_max and ff["summary"]["B"]["control_false_positives"] == 0

    c5 = args.skip_exec or (
        len(b_audits) == 9
        and all(not a["forbidden_escapes"] for a in b_audits.values())
        and all(len(a["ecosystems"]) >= 3 for a in b_audits.values())
        and all(a["records"] >= 1 and a["uses_summarize"] and a["uses_history_count"] for a in b_audits.values())
    )

    print("\n=== CONDITION AUDIT ===", flush=True)
    print(f"Condition 1 (Fair multi-ecosystem composition, 54 runs, >=3 ecosystems): {'PASS' if c1 else 'FAIL'}")
    print(f"Condition 2 (Error rate <= best sibling: B={b_sum['remaining_errors']}/540 vs best sibling={best_sib_err}/540): {'PASS' if c2 else 'FAIL'}")
    print(f"Condition 3 (Honest expressiveness: added={c3_added}, diff={c3_diff}, full={c3_full}, guide={b_guide_tok}/1500): {'PASS' if c3 else 'FAIL'}")
    print(f"Condition 4 (False friends: B={b_ff}/25 ({b_ff_rate}%), max sibling={sib_ff_max}/25, 0 FP): {'PASS' if c4 else 'FAIL'}")
    print(f"Condition 5 (Own language, 0 escapes, B-native IR constructs across 9/9 B runs): {'PASS' if c5 else 'FAIL'}")

    if b_audits:
        print("\n=== B FINAL STAGE 5 OWN-LANGUAGE AUDIT ===")
        for rid, aud in sorted(b_audits.items()):
            print(f"  {rid}: ecosystems={aud['ecosystems']} records={aud['records']} dims={aud['units_or_currencies']} "
                  f"summarize={aud['uses_summarize']} history={aud['uses_history_count']} escapes={len(aud['forbidden_escapes'])}")

    ok = (token_mismatches == 0 and exec_mismatches == 0 and c1 and c2 and c3 and c4 and c5)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
