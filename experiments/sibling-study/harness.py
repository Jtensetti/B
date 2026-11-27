#!/usr/bin/env python3
"""Study B Harness: isolated workspaces, fixed-budget ./submit gatekeeper, hidden oracle grader,
o200k_base token accounting, and Condition 1/2/3/5 aggregator.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STUDY_DIR = Path(__file__).resolve().parent
TOOLS_NM = STUDY_DIR / "tools" / "node_modules"
TSC_BIN = TOOLS_NM / ".bin" / "tsc"
TOKENIZER = STUDY_DIR / "tokenize_o200k.mjs"
STATE_DIR = STUDY_DIR / "state"
SNAP_DIR = STUDY_DIR / "snapshots"
WORK_ROOT = STUDY_DIR / "workspaces"
CARGO_SHARED_TARGET = STUDY_DIR / "tools" / "cargo_target"

sys.path.insert(0, str(STUDY_DIR))
import tasks as study_tasks  # noqa: E402

MAX_ATTEMPTS_PER_STAGE = 3
LANGS = ("B", "Python", "C#", "TypeScript", "Go", "Rust")

SRC_FILES = {
    "B": "solution.bee",
    "Python": "solution.py",
    "C#": "Program.cs",
    "TypeScript": "solution.ts",
    "Go": "main.go",
    "Rust": "src/main.rs",
}


def count_o200k(text: str) -> int:
    proc = subprocess.run(
        ["node", str(TOKENIZER), "--stdin"],
        input=text, capture_output=True, text=True, check=True, timeout=15,
    )
    return int(json.loads(proc.stdout)["tokens"])


def compute_diff_tokens(prev_text: str, curr_text: str) -> tuple[int, int]:
    """Return (added_lines_tokens, unified_diff_tokens) from prev_text -> curr_text."""
    if not prev_text:
        full = count_o200k(curr_text)
        return full, full
    diff_lines = list(difflib.unified_diff(
        prev_text.splitlines(keepends=True),
        curr_text.splitlines(keepends=True),
        lineterm="",
    ))
    body = [ln for ln in diff_lines if not ln.startswith(("---", "+++", "@@"))]
    added = "".join(ln[1:] for ln in body if ln.startswith("+"))
    diff_payload = "".join(body)
    return count_o200k(added), count_o200k(diff_payload)


def state_path(run_id: str) -> Path:
    return STATE_DIR / f"{run_id}.json"


def load_state(run_id: str) -> dict[str, Any]:
    return json.loads(state_path(run_id).read_text(encoding="utf-8"))


def save_state(run_id: str, data: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_path(run_id).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def init_workspace(task_id: str, lang: str, solver_id: int) -> Path:
    assert task_id in study_tasks.TASKS
    assert lang in LANGS
    safe_lang = lang.lower().replace("#", "sharp")
    run_id = f"{task_id}__{safe_lang}__s{solver_id}"
    ws = WORK_ROOT / run_id
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True, exist_ok=True)

    # Create EMPTY target source file (Condition 1: from empty file!)
    src_rel = SRC_FILES[lang]
    src_path = ws / src_rel
    src_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.write_text("", encoding="utf-8")

    # Minimal build/config scaffolding per language
    if lang == "B":
        (ws / "node_modules").symlink_to(TOOLS_NM)
        shutil.copy(STUDY_DIR / "B_GUIDE.md", ws / "B_GUIDE.md")
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
        (ws / "node_modules").symlink_to(TOOLS_NM)
        (ws / "tsconfig.json").write_text(json.dumps({
            "compilerOptions": {
                "target": "ES2022",
                "module": "CommonJS",
                "moduleResolution": "node",
                "esModuleInterop": True,
                "strict": True,
                "outDir": "dist",
                "skipLibCheck": True,
                "typeRoots": [str(TOOLS_NM / "@types")],
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

    shutil.copy(STUDY_DIR / "SIBLING_GUIDE.md", ws / "GUIDE.md")
    (ws / "STAGE.md").write_text(study_tasks.render_stage_md(task_id, 0, lang), encoding="utf-8")

    submit_sh = ws / "submit"
    submit_sh.write_text(
        f"#!/usr/bin/env bash\nset -euo pipefail\nexec {sys.executable} {Path(__file__).resolve()} submit {run_id}\n",
        encoding="utf-8",
    )
    submit_sh.chmod(submit_sh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    state = {
        "run_id": run_id,
        "task_id": task_id,
        "lang": lang,
        "solver_id": solver_id,
        "workspace": str(ws),
        "current_stage": 0,
        "completed": False,
        "stages": {
            str(k): {
                "attempts": [],
                "public_passed": False,
                "hidden_passed": None,
                "hidden_total": None,
                "hidden_failures": [],
            }
            for k in range(6)
        },
        "last_submitted_source": "",
        "own_language_audit": None,
    }
    save_state(run_id, state)
    return ws


def check_and_build(ws: Path, lang: str, task_id: str) -> tuple[bool, str, list[str] | None, dict[str, Any]]:
    """Run static check/compile and return (ok, diagnostics, exec_cmd, audit_info)."""
    env = os.environ.copy()
    audit: dict[str, Any] = {}
    if lang == "B":
        bee = ws / "solution.bee"
        src = bee.read_text(encoding="utf-8")
        # Condition 5 check: reject raw embedded host code escape hatches
        forbidden = re.findall(r"\b(eval|exec|__import__|subprocess|os\.system)\b", src)
        if forbidden:
            return False, f"E_OWN_LANG: Forbidden host escape hatch detected: {forbidden}", None, audit
        proc = subprocess.run(
            [sys.executable, "-m", "b_lang.cli", "check", str(bee), "--strict", "--json"],
            cwd=str(ws), capture_output=True, text=True, check=False, timeout=30,
        )
        if proc.returncode != 0:
            return False, (proc.stderr or proc.stdout).strip(), None, audit
        # Verify BIR uses all 3 required ecosystems for this task!
        ir_proc = subprocess.run(
            [sys.executable, "-m", "b_lang.cli", "ir", str(bee), "--strict"],
            cwd=str(ws), capture_output=True, text=True, check=False, timeout=30,
        )
        if ir_proc.returncode != 0:
            return False, (ir_proc.stderr or ir_proc.stdout).strip(), None, audit
        ir = json.loads(ir_proc.stdout)
        used_backends = sorted({sym["backend"] for sym in ir.get("foreign_symbols", [])})
        required = list(study_tasks.TASKS[task_id]["b_required_ecosystems"])
        missing = [b for b in required if b not in used_backends]
        audit = {"used_backends": used_backends, "foreign_count": len(ir.get("foreign_symbols", []))}
        if missing:
            return False, f"E_ECOSYSTEM: Missing required ecosystem call(s) in B program: {missing} (used: {used_backends})", None, audit
        return True, "", [sys.executable, "-m", "b_lang.cli", "run", str(bee)], audit

    if lang == "Python":
        py = ws / "solution.py"
        proc = subprocess.run(
            ["mypy", "--strict", "--no-incremental", "--cache-dir=/dev/null", str(py)],
            cwd=str(ws), capture_output=True, text=True, check=False, timeout=30,
        )
        if proc.returncode != 0:
            return False, (proc.stdout + "\n" + proc.stderr).strip(), None, audit
        return True, "", [sys.executable, str(py)], audit

    if lang == "C#":
        proc = subprocess.run(
            ["dotnet", "build", "--nologo", "-v", "quiet"],
            cwd=str(ws), capture_output=True, text=True, check=False, timeout=60,
        )
        if proc.returncode != 0:
            return False, (proc.stdout + "\n" + proc.stderr).strip(), None, audit
        dll = ws / "bin" / "Debug" / "net10.0" / "App.dll"
        return True, "", ["dotnet", str(dll)], audit

    if lang == "TypeScript":
        proc = subprocess.run(
            [str(TSC_BIN), "-p", str(ws / "tsconfig.json")],
            cwd=str(ws), capture_output=True, text=True, check=False, timeout=30,
        )
        if proc.returncode != 0:
            return False, (proc.stdout + "\n" + proc.stderr).strip(), None, audit
        return True, "", ["node", str(ws / "dist" / "solution.js")], audit

    if lang == "Go":
        v = subprocess.run(["go", "vet", "./..."], cwd=str(ws), capture_output=True, text=True, check=False, timeout=30)
        if v.returncode != 0:
            return False, (v.stdout + "\n" + v.stderr).strip(), None, audit
        b = subprocess.run(["go", "build", "-o", str(ws / "app.bin"), "."], cwd=str(ws), capture_output=True, text=True, check=False, timeout=30)
        if b.returncode != 0:
            return False, (b.stdout + "\n" + b.stderr).strip(), None, audit
        return True, "", [str(ws / "app.bin")], audit

    if lang == "Rust":
        env["RUSTFLAGS"] = "-D warnings"
        env["CARGO_TARGET_DIR"] = str(CARGO_SHARED_TARGET)
        b = subprocess.run(
            ["cargo", "build", "--quiet", "--offline"],
            cwd=str(ws), env=env, capture_output=True, text=True, check=False, timeout=120,
        )
        if b.returncode != 0:
            # Fallback without --offline if cache wasn't warmed yet
            b = subprocess.run(
                ["cargo", "build", "--quiet"],
                cwd=str(ws), env=env, capture_output=True, text=True, check=False, timeout=120,
            )
        if b.returncode != 0:
            return False, (b.stdout + "\n" + b.stderr).strip(), None, audit
        pkg_name = re.sub(r"[^a-z0-9_]", "_", ws.name.lower())
        bin_path = CARGO_SHARED_TARGET / "debug" / pkg_name
        local_bin = ws / "solution.bin"
        shutil.copy2(bin_path, local_bin)
        return True, "", [str(local_bin)], audit

    raise ValueError(f"Unknown lang {lang}")


def run_cases(cmd: list[str], ws: Path, lang: str, stage: int, task_id: str,
              cases: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    env = os.environ.copy()
    if lang == "TypeScript":
        env["NODE_PATH"] = str(TOOLS_NM)
    oracle = study_tasks.TASKS[task_id]["oracle"]
    passed = 0
    failures: list[dict[str, Any]] = []
    for idx, inp in enumerate(cases):
        expected = oracle(stage, inp)
        try:
            proc = subprocess.run(
                cmd, cwd=str(ws), env=env, input=json.dumps(inp),
                capture_output=True, text=True, check=False, timeout=20,
            )
        except subprocess.TimeoutExpired:
            failures.append({"case": idx, "error": "timeout"})
            continue
        if proc.returncode != 0:
            failures.append({"case": idx, "error": f"exit {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:200]}"})
            continue
        try:
            actual = json.loads(proc.stdout.strip())
        except json.JSONDecodeError as exc:
            failures.append({"case": idx, "error": f"invalid JSON stdout ({exc.msg}): {proc.stdout.strip()[:200]}"})
            continue
        if actual == expected:
            passed += 1
        else:
            failures.append({"case": idx, "expected": expected, "actual": actual})
    return passed, failures


def cmd_submit(run_id: str) -> int:
    state = load_state(run_id)
    stage = state["current_stage"]
    stage_rec = state["stages"][str(stage)]
    attempts = stage_rec["attempts"]
    if len(attempts) >= MAX_ATTEMPTS_PER_STAGE:
        print(f"REJECTED: budget exhausted ({MAX_ATTEMPTS_PER_STAGE}/{MAX_ATTEMPTS_PER_STAGE} attempts used for stage {stage}).", file=sys.stderr)
        return 1

    ws = Path(state["workspace"])
    lang = state["lang"]
    task_id = state["task_id"]
    src_path = ws / SRC_FILES[lang]
    src_text = src_path.read_text(encoding="utf-8")

    attempt_num = len(attempts) + 1
    snap_dir = SNAP_DIR / run_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_file = snap_dir / f"stage_{stage}_attempt_{attempt_num}{Path(SRC_FILES[lang]).suffix}"
    snap_file.write_text(src_text, encoding="utf-8")

    full_tok = count_o200k(src_text)
    added_tok, diff_tok = compute_diff_tokens(state["last_submitted_source"], src_text)
    state["last_submitted_source"] = src_text

    ok_build, diag, exec_cmd, audit = check_and_build(ws, lang, task_id)
    rec: dict[str, Any] = {
        "attempt": attempt_num,
        "snapshot": str(snap_file.relative_to(STUDY_DIR)),
        "full_tokens": full_tok,
        "added_tokens": added_tok,
        "diff_tokens": diff_tok,
        "bytes": len(src_text.encode("utf-8")),
        "lines": len(src_text.splitlines()),
        "compile_ok": ok_build,
        "public_passed": False,
        "audit": audit,
    }

    if not ok_build or exec_cmd is None:
        rec["error"] = diag[:1000]
        attempts.append(rec)
        save_state(run_id, state)
        print(f"COMPILE/CHECK FAILED (attempt {attempt_num}/{MAX_ATTEMPTS_PER_STAGE}):\n{diag[:1200]}", file=sys.stderr)
        return 1

    pub_cases = study_tasks.TASKS[task_id]["public"](stage)
    pub_passed, pub_fail = run_cases(exec_cmd, ws, lang, stage, task_id, pub_cases)
    rec["public_passed"] = (pub_passed == len(pub_cases))
    if pub_fail:
        rec["public_failures"] = pub_fail
    attempts.append(rec)
    stage_rec["public_passed"] = rec["public_passed"]
    save_state(run_id, state)

    if rec["public_passed"]:
        print(f"ACCEPTED (public checks {pub_passed}/{len(pub_cases)} passed, attempt {attempt_num}/{MAX_ATTEMPTS_PER_STAGE}, full_tokens={full_tok}, delta_tokens={added_tok})")
        return 0
    first = pub_fail[0]
    print(f"PUBLIC CHECK FAILED ({pub_passed}/{len(pub_cases)} passed, attempt {attempt_num}/{MAX_ATTEMPTS_PER_STAGE}):\n"
          f"Example #{first['case'] + 1}: {json.dumps(first, ensure_ascii=False)}", file=sys.stderr)
    return 1


def cmd_advance(run_id: str) -> int:
    """Grade current stage on hidden independent oracle and advance to next stage."""
    state = load_state(run_id)
    stage = state["current_stage"]
    stage_rec = state["stages"][str(stage)]
    ws = Path(state["workspace"])
    lang = state["lang"]
    task_id = state["task_id"]

    hid_cases = study_tasks.TASKS[task_id]["hidden"](stage)
    if not stage_rec["attempts"]:
        stage_rec["hidden_passed"] = 0
        stage_rec["hidden_total"] = len(hid_cases)
        stage_rec["hidden_failures"] = [{"case": -1, "error": "no submission"}]
    else:
        # Restore exact last submitted snapshot before hidden grading
        last_snap = STUDY_DIR / stage_rec["attempts"][-1]["snapshot"]
        (ws / SRC_FILES[lang]).write_text(last_snap.read_text(encoding="utf-8"), encoding="utf-8")
        ok_build, diag, exec_cmd, audit = check_and_build(ws, lang, task_id)
        if not ok_build or exec_cmd is None:
            stage_rec["hidden_passed"] = 0
            stage_rec["hidden_total"] = len(hid_cases)
            stage_rec["hidden_failures"] = [{"case": -1, "error": f"compile failed: {diag[:200]}"}]
        else:
            passed, failures = run_cases(exec_cmd, ws, lang, stage, task_id, hid_cases)
            stage_rec["hidden_passed"] = passed
            stage_rec["hidden_total"] = len(hid_cases)
            stage_rec["hidden_failures"] = failures
            if stage == 5:
                state["own_language_audit"] = audit

    if stage < 5:
        state["current_stage"] = stage + 1
        (ws / "STAGE.md").write_text(study_tasks.render_stage_md(task_id, stage + 1, lang), encoding="utf-8")
    else:
        state["completed"] = True
    save_state(run_id, state)
    print(json.dumps({
        "run_id": run_id,
        "graded_stage": stage,
        "hidden_passed": stage_rec["hidden_passed"],
        "hidden_total": stage_rec["hidden_total"],
        "attempts": len(stage_rec["attempts"]),
        "next_stage": None if state["completed"] else state["current_stage"],
    }))
    return 0


def cmd_aggregate() -> int:
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(STATE_DIR.glob("*.json"))]
    by_lang: dict[str, list[dict[str, Any]]] = {l: [] for l in LANGS}
    for r in runs:
        if r.get("completed"):
            by_lang[r["lang"]].append(r)

    summary: dict[str, Any] = {}
    for lang in LANGS:
        lruns = by_lang[lang]
        if not lruns:
            continue
        total_hidden_cases = 0
        total_hidden_passed = 0
        total_attempts = 0
        total_full_tokens = 0
        total_added_tokens = 0
        total_diff_tokens = 0
        final_stage5_tokens = []
        per_task: dict[str, dict[str, Any]] = {}
        for r in lruns:
            tid = r["task_id"]
            t_hid_p = t_hid_tot = t_att = t_full = t_add = t_diff = 0
            for k in range(6):
                sr = r["stages"][str(k)]
                t_hid_p += sr["hidden_passed"] or 0
                t_hid_tot += sr["hidden_total"] or 0
                t_att += len(sr["attempts"])
                for a in sr["attempts"]:
                    t_full += a["full_tokens"]
                    t_add += a["added_tokens"]
                    t_diff += a["diff_tokens"]
            last5 = r["stages"]["5"]["attempts"][-1]["full_tokens"] if r["stages"]["5"]["attempts"] else 0
            final_stage5_tokens.append(last5)
            total_hidden_passed += t_hid_p
            total_hidden_cases += t_hid_tot
            total_attempts += t_att
            total_full_tokens += t_full
            total_added_tokens += t_add
            total_diff_tokens += t_diff
            bucket = per_task.setdefault(tid, {"runs": 0, "errors": 0, "cases": 0, "attempts": 0, "added_tokens": 0, "full_tokens": 0, "final_tokens": 0})
            bucket["runs"] += 1
            bucket["errors"] += (t_hid_tot - t_hid_p)
            bucket["cases"] += t_hid_tot
            bucket["attempts"] += t_att
            bucket["added_tokens"] += t_add
            bucket["full_tokens"] += t_full
            bucket["final_tokens"] += last5

        n = len(lruns)
        summary[lang] = {
            "completed_runs": n,
            "hidden_passed": total_hidden_passed,
            "hidden_total": total_hidden_cases,
            "remaining_errors": total_hidden_cases - total_hidden_passed,
            "total_attempts": total_attempts,
            "mean_attempts_per_run": round(total_attempts / n, 2),
            "total_lifecycle_added_tokens": total_added_tokens,
            "mean_lifecycle_added_tokens": round(total_added_tokens / n, 1),
            "total_lifecycle_diff_tokens": total_diff_tokens,
            "mean_lifecycle_diff_tokens": round(total_diff_tokens / n, 1),
            "total_lifecycle_full_tokens": total_full_tokens,
            "mean_lifecycle_full_tokens": round(total_full_tokens / n, 1),
            "mean_final_stage5_tokens": round(sum(final_stage5_tokens) / n, 1),
            "per_task": per_task,
        }

    b_guide_tok = count_o200k((STUDY_DIR / "B_GUIDE.md").read_text(encoding="utf-8"))
    report = {
        "study": "sibling-multi-ecosystem-lifecycle",
        "b_guide_o200k_tokens": b_guide_tok,
        "b_guide_cap_tokens": 1500,
        "max_attempts_per_stage": MAX_ATTEMPTS_PER_STAGE,
        "summary": summary,
    }
    (STUDY_DIR / "results.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("Usage: harness.py init <task> <lang> <solver_id> | submit <run_id> | advance <run_id> | aggregate", file=sys.stderr)
        return 2
    cmd = args[0]
    if cmd == "init":
        ws = init_workspace(args[1], args[2], int(args[3]))
        print(str(ws))
        return 0
    if cmd == "submit":
        return cmd_submit(args[1])
    if cmd == "advance":
        return cmd_advance(args[1])
    if cmd == "aggregate":
        return cmd_aggregate()
    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
