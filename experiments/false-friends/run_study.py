#!/usr/bin/env python3
"""Executable preregistered Study A: 25 planted boundary faults + 5 controls across 6 languages.

Runs real static checks / compilers / dependency-lock verifiers WITHOUT executing
the candidate applications:
  - B:            b check --strict [--lock lock.json]
  - Typed Python: mypy --strict
  - C#:           dotnet build (Nullable=enable, TreatWarningsAsErrors=true)
  - TypeScript:   tsc --strict --noEmit
  - Go:           go vet && go build
  - Rust:         rustc -D warnings (compile only)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
STUDY_DIR = Path(__file__).resolve().parent
TSC_BIN = ROOT / "experiments" / "sibling-study" / "tools" / "node_modules" / ".bin" / "tsc"
NODE_MODULES = ROOT / "experiments" / "sibling-study" / "tools" / "node_modules"


def run_cmd(cmd: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int = 60) -> tuple[int, str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    proc = subprocess.run(cmd, cwd=str(cwd), env=full_env, capture_output=True, text=True, check=False, timeout=timeout)
    return proc.returncode, (proc.stderr + "\n" + proc.stdout).strip()


# ---------------------------------------------------------------------------
# Language checker adapters (NEVER execute the candidate program!)
# ---------------------------------------------------------------------------

def check_b(work: Path, source: str, *, lock_setup: Callable[[Path], None] | None = None,
            mutate_after_lock: Callable[[Path], None] | None = None) -> tuple[bool, str]:
    d = work / "b"
    d.mkdir(parents=True, exist_ok=True)
    # Symlink node_modules so js: packages resolve next to the .bee file
    nm = d / "node_modules"
    if not nm.exists() and NODE_MODULES.is_dir():
        nm.symlink_to(NODE_MODULES)
    bee = d / "main.bee"
    bee.write_text(source, encoding="utf-8")
    env = {"PYTHONPATH": str(d) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    lock_file = d / "main.bee.lock.json"
    if lock_setup is not None:
        lock_setup(d)
        rc, out = run_cmd([sys.executable, "-m", "b_lang.cli", "lock", str(bee), "--out", str(lock_file)], d, env)
        if rc != 0:
            # Lock creation itself rejected statically (e.g. E_UNIT/E_FALSE_FRIEND)
            return True, out
        if mutate_after_lock is not None:
            mutate_after_lock(d)
        rc, out = run_cmd([sys.executable, "-m", "b_lang.cli", "check", str(bee), "--strict", "--lock", str(lock_file)], d, env)
        return rc != 0, out
    rc, out = run_cmd([sys.executable, "-m", "b_lang.cli", "check", str(bee), "--strict"], d, env)
    return rc != 0, out


def check_python(work: Path, files: dict[str, str]) -> tuple[bool, str]:
    d = work / "py"
    d.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    rc, out = run_cmd(["mypy", "--strict", "--no-incremental", "--cache-dir=/dev/null", str(d / "main.py")], d)
    return rc != 0, out


def check_csharp(work: Path, files: dict[str, str]) -> tuple[bool, str]:
    d = work / "cs"
    d.mkdir(parents=True, exist_ok=True)
    csproj = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net10.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
  </PropertyGroup>
</Project>
"""
    (d / "App.csproj").write_text(csproj, encoding="utf-8")
    for rel, content in files.items():
        (d / rel).write_text(content, encoding="utf-8")
    rc, out = run_cmd(["dotnet", "build", "--nologo", "-v", "quiet"], d)
    return rc != 0, out


def check_typescript(work: Path, files: dict[str, str]) -> tuple[bool, str]:
    d = work / "ts"
    d.mkdir(parents=True, exist_ok=True)
    tsconfig = {
        "compilerOptions": {
            "target": "ES2022",
            "module": "CommonJS",
            "strict": True,
            "noEmit": True,
            "skipLibCheck": True,
            "allowJs": True,
            "typeRoots": [str(NODE_MODULES / "@types")],
        },
        "include": ["main.ts"],
    }
    (d / "tsconfig.json").write_text(json.dumps(tsconfig), encoding="utf-8")
    for rel, content in files.items():
        (d / rel).write_text(content, encoding="utf-8")
    rc, out = run_cmd([str(TSC_BIN), "-p", str(d / "tsconfig.json")], d)
    return rc != 0, out


def check_go(work: Path, files: dict[str, str]) -> tuple[bool, str]:
    d = work / "go"
    d.mkdir(parents=True, exist_ok=True)
    (d / "go.mod").write_text("module caseapp\n\ngo 1.24\n", encoding="utf-8")
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    rc, out = run_cmd(["go", "vet", "./..."], d)
    if rc != 0:
        return True, out
    rc, out = run_cmd(["go", "build", "-o", str(d / "app.bin"), "."], d)
    return rc != 0, out


def check_rust(work: Path, files: dict[str, str]) -> tuple[bool, str]:
    d = work / "rs"
    d.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    rc, out = run_cmd(["rustc", "--edition=2021", "-D", "warnings", str(d / "main.rs"), "-o", str(d / "app.bin")], d)
    return rc != 0, out


# ---------------------------------------------------------------------------
# Case builder helpers
# ---------------------------------------------------------------------------

def make_py_dep(code_v1: str, code_v2: str, mod_name: str = "depmod"):
    def setup(d: Path):
        (d / f"{mod_name}.py").write_text(code_v1, encoding="utf-8")

    def mutate(d: Path):
        (d / f"{mod_name}.py").write_text(code_v2, encoding="utf-8")

    return setup, mutate


def make_js_dep(code_v1: str, code_v2: str, pkg_name: str = "dep-pkg"):
    def write_pkg(d: Path, body: str, ver: str):
        p = d / "local_pkgs" / "node_modules" / pkg_name
        p.mkdir(parents=True, exist_ok=True)
        (p / "package.json").write_text(json.dumps({"name": pkg_name, "version": ver, "main": "index.cjs"}), encoding="utf-8")
        (p / "index.cjs").write_text(body, encoding="utf-8")
        # Override symlink so d/node_modules is a real dir containing dep-pkg
        nm = d / "node_modules"
        if nm.is_symlink():
            nm.unlink()
        nm.mkdir(exist_ok=True)
        target = nm / pkg_name
        if target.exists() or target.is_symlink():
            if target.is_symlink():
                target.unlink()
            else:
                shutil.rmtree(target)
        target.symlink_to(p)

    return (lambda d: write_pkg(d, code_v1, "1.0.0")), (lambda d: write_pkg(d, code_v2, "1.0.1"))


# ---------------------------------------------------------------------------
# 25 Preregistered Planted Boundary Faults + 5 Clean Controls
# ---------------------------------------------------------------------------

def build_cases() -> list[dict]:
    cases: list[dict] = []

    # ===== CATEGORY 1: WRONG UNIT (U1-U5) =====
    cases.append({
        "id": "U1_add_m_and_km",
        "category": "wrong_unit",
        "is_control": False,
        "description": "Add meters directly to kilometers without unit conversion",
        "b": ("unit m\nunit km = 1000 m\nfn total(a_m: Float[m], b_km: Float[km]) -> Float[m] pure = a_m + b_km\n", None, None),
        "py": {"main.py": "def total(a_m: float, b_km: float) -> float:\n    return a_m + b_km\nprint(total(500.0, 2.0))\n"},
        "cs": {"Program.cs": "static double Total(double aM, double bKm) => aM + bKm;\nConsole.WriteLine(Total(500.0, 2.0));\n"},
        "ts": {"main.ts": "function total(aM: number, bKm: number): number { return aM + bKm; }\nconsole.log(total(500.0, 2.0));\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc total(aM float64, bKm float64) float64 { return aM + bKm }\nfunc main() { fmt.Println(total(500.0, 2.0)) }\n"},
        "rs": {"main.rs": "fn total(a_m: f64, b_km: f64) -> f64 { a_m + b_km }\nfn main() { println!(\"{}\", total(500.0, 2.0)); }\n"},
    })

    cases.append({
        "id": "U2_pass_ms_as_s",
        "category": "wrong_unit",
        "is_control": False,
        "description": "Pass milliseconds into a function expecting seconds",
        "b": ("unit s\nunit ms = 0.001 s\nfn deadline(wait_s: Float[s]) -> Float[s] pure = wait_s + (5.0 as s)\nlet d = deadline(250.0 as ms)\n", None, None),
        "py": {"main.py": "def deadline(wait_s: float) -> float:\n    return wait_s + 5.0\nwait_ms: float = 250.0\nprint(deadline(wait_ms))\n"},
        "cs": {"Program.cs": "static double Deadline(double waitS) => waitS + 5.0;\ndouble waitMs = 250.0;\nConsole.WriteLine(Deadline(waitMs));\n"},
        "ts": {"main.ts": "function deadline(waitS: number): number { return waitS + 5.0; }\nconst waitMs: number = 250.0;\nconsole.log(deadline(waitMs));\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc deadline(waitS float64) float64 { return waitS + 5.0 }\nfunc main() { waitMs := 250.0; fmt.Println(deadline(waitMs)) }\n"},
        "rs": {"main.rs": "fn deadline(wait_s: f64) -> f64 { wait_s + 5.0 }\nfn main() { let wait_ms: f64 = 250.0; println!(\"{}\", deadline(wait_ms)); }\n"},
    })

    cases.append({
        "id": "U3_compare_kg_and_g",
        "category": "wrong_unit",
        "is_control": False,
        "description": "Compare weight in kg directly against threshold in grams",
        "b": ("unit kg\nunit g = 0.001 kg\nfn overweight(w_kg: Float[kg], max_g: Float[g]) -> Bool pure = w_kg > max_g\n", None, None),
        "py": {"main.py": "def overweight(w_kg: float, max_g: float) -> bool:\n    return w_kg > max_g\nprint(overweight(1.5, 500.0))\n"},
        "cs": {"Program.cs": "static bool Overweight(double wKg, double maxG) => wKg > maxG;\nConsole.WriteLine(Overweight(1.5, 500.0));\n"},
        "ts": {"main.ts": "function overweight(wKg: number, maxG: number): boolean { return wKg > maxG; }\nconsole.log(overweight(1.5, 500.0));\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc overweight(wKg float64, maxG float64) bool { return wKg > maxG }\nfunc main() { fmt.Println(overweight(1.5, 500.0)) }\n"},
        "rs": {"main.rs": "fn overweight(w_kg: f64, max_g: f64) -> bool { w_kg > max_g }\nfn main() { println!(\"{}\", overweight(1.5, 500.0)); }\n"},
    })

    cases.append({
        "id": "U4_untagged_float_as_km",
        "category": "wrong_unit",
        "is_control": False,
        "description": "Pass bare dimensionless float into a km-typed routing function",
        "b": ("unit km\nfn range_ok(dist: Float[km]) -> Bool pure = dist <= (100.0 as km)\nlet ok = range_ok(42.0)\n", None, None),
        "py": {"main.py": "def range_ok(dist_km: float) -> bool:\n    return dist_km <= 100.0\nraw_val: float = 42.0\nprint(range_ok(raw_val))\n"},
        "cs": {"Program.cs": "static bool RangeOk(double distKm) => distKm <= 100.0;\ndouble rawVal = 42.0;\nConsole.WriteLine(RangeOk(rawVal));\n"},
        "ts": {"main.ts": "function rangeOk(distKm: number): boolean { return distKm <= 100.0; }\nconst rawVal: number = 42.0;\nconsole.log(rangeOk(rawVal));\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc rangeOk(distKm float64) bool { return distKm <= 100.0 }\nfunc main() { rawVal := 42.0; fmt.Println(rangeOk(rawVal)) }\n"},
        "rs": {"main.rs": "fn range_ok(dist_km: f64) -> bool { dist_km <= 100.0 }\nfn main() { let raw_val: f64 = 42.0; println!(\"{}\", range_ok(raw_val)); }\n"},
    })

    cases.append({
        "id": "U5_cross_dimension_m_to_s",
        "category": "wrong_unit",
        "is_control": False,
        "description": "Convert meters into seconds (incompatible physical dimensions)",
        "b": ("unit m, s\nlet bad: Float[s] = (10.0 as m) to s\n", None, None),
        "py": {"main.py": "meters: float = 10.0\nseconds: float = meters\nprint(seconds)\n"},
        "cs": {"Program.cs": "double meters = 10.0;\ndouble seconds = meters;\nConsole.WriteLine(seconds);\n"},
        "ts": {"main.ts": "const meters: number = 10.0;\nconst seconds: number = meters;\nconsole.log(seconds);\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc main() { meters := 10.0; seconds := meters; fmt.Println(seconds) }\n"},
        "rs": {"main.rs": "fn main() { let meters: f64 = 10.0; let seconds: f64 = meters; println!(\"{}\", seconds); }\n"},
    })

    # ===== CATEGORY 2: WRONG CURRENCY (C1-C5) =====
    cases.append({
        "id": "C1_add_sek_and_eur",
        "category": "wrong_currency",
        "is_control": False,
        "description": "Add SEK item price directly to EUR shipping fee",
        "b": ("currency SEK, EUR\nfn invoice(item: Float[SEK], ship: Float[EUR]) -> Float[SEK] pure = item + ship\n", None, None),
        "py": {"main.py": "def invoice(item_sek: float, ship_eur: float) -> float:\n    return item_sek + ship_eur\nprint(invoice(100.0, 10.0))\n"},
        "cs": {"Program.cs": "static decimal Invoice(decimal itemSek, decimal shipEur) => itemSek + shipEur;\nConsole.WriteLine(Invoice(100m, 10m));\n"},
        "ts": {"main.ts": "function invoice(itemSek: number, shipEur: number): number { return itemSek + shipEur; }\nconsole.log(invoice(100, 10));\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc invoice(itemSek float64, shipEur float64) float64 { return itemSek + shipEur }\nfunc main() { fmt.Println(invoice(100, 10)) }\n"},
        "rs": {"main.rs": "fn invoice(item_sek: f64, ship_eur: f64) -> f64 { item_sek + ship_eur }\nfn main() { println!(\"{}\", invoice(100.0, 10.0)); }\n"},
    })

    cases.append({
        "id": "C2_pass_usd_to_eur_api",
        "category": "wrong_currency",
        "is_control": False,
        "description": "Pass USD amount to a billing function expecting EUR",
        "b": ("currency USD, EUR\nfn charge_eur(amt: Float[EUR]) -> Float[EUR] pure = amt * 1.25\nlet total = charge_eur(50.0 as USD)\n", None, None),
        "py": {"main.py": "def charge_eur(amt_eur: float) -> float:\n    return amt_eur * 1.25\namt_usd: float = 50.0\nprint(charge_eur(amt_usd))\n"},
        "cs": {"Program.cs": "static decimal ChargeEur(decimal amtEur) => amtEur * 1.25m;\ndecimal amtUsd = 50m;\nConsole.WriteLine(ChargeEur(amtUsd));\n"},
        "ts": {"main.ts": "function chargeEur(amtEur: number): number { return amtEur * 1.25; }\nconst amtUsd: number = 50;\nconsole.log(chargeEur(amtUsd));\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc chargeEur(amtEur float64) float64 { return amtEur * 1.25 }\nfunc main() { amtUsd := 50.0; fmt.Println(chargeEur(amtUsd)) }\n"},
        "rs": {"main.rs": "fn charge_eur(amt_eur: f64) -> f64 { amt_eur * 1.25 }\nfn main() { let amt_usd: f64 = 50.0; println!(\"{}\", charge_eur(amt_usd)); }\n"},
    })

    cases.append({
        "id": "C3_return_sek_as_eur",
        "category": "wrong_currency",
        "is_control": False,
        "description": "Function promises EUR return value but returns SEK amount",
        "b": ("currency SEK, EUR\nfn quote_eur(base: Float[SEK]) -> Float[EUR] pure = base\n", None, None),
        "py": {"main.py": "def quote_eur(base_sek: float) -> float:\n    return base_sek\nprint(quote_eur(250.0))\n"},
        "cs": {"Program.cs": "static decimal QuoteEur(decimal baseSek) => baseSek;\nConsole.WriteLine(QuoteEur(250m));\n"},
        "ts": {"main.ts": "function quoteEur(baseSek: number): number { return baseSek; }\nconsole.log(quoteEur(250));\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc quoteEur(baseSek float64) float64 { return baseSek }\nfunc main() { fmt.Println(quoteEur(250)) }\n"},
        "rs": {"main.rs": "fn quote_eur(base_sek: f64) -> f64 { base_sek }\nfn main() { println!(\"{}\", quote_eur(250.0)); }\n"},
    })

    cases.append({
        "id": "C4_compare_sek_vs_eur",
        "category": "wrong_currency",
        "is_control": False,
        "description": "Compare SEK invoice directly against EUR approval cap",
        "b": ("currency SEK, EUR\nfn needs_approval(inv: Float[SEK], cap: Float[EUR]) -> Bool pure = inv > cap\n", None, None),
        "py": {"main.py": "def needs_approval(inv_sek: float, cap_eur: float) -> bool:\n    return inv_sek > cap_eur\nprint(needs_approval(900.0, 100.0))\n"},
        "cs": {"Program.cs": "static bool NeedsApproval(decimal invSek, decimal capEur) => invSek > capEur;\nConsole.WriteLine(NeedsApproval(900m, 100m));\n"},
        "ts": {"main.ts": "function needsApproval(invSek: number, capEur: number): boolean { return invSek > capEur; }\nconsole.log(needsApproval(900, 100));\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc needsApproval(invSek float64, capEur float64) bool { return invSek > capEur }\nfunc main() { fmt.Println(needsApproval(900, 100)) }\n"},
        "rs": {"main.rs": "fn needs_approval(inv_sek: f64, cap_eur: f64) -> bool { inv_sek > cap_eur }\nfn main() { println!(\"{}\", needs_approval(900.0, 100.0)); }\n"},
    })

    cases.append({
        "id": "C5_implicit_fx_convert",
        "category": "wrong_currency",
        "is_control": False,
        "description": "Attempt implicit currency conversion without exchange rate",
        "b": ("currency SEK, EUR\nlet bad: Float[EUR] = (100.0 as SEK) to EUR\n", None, None),
        "py": {"main.py": "amount_sek: float = 100.0\namount_eur: float = amount_sek\nprint(amount_eur)\n"},
        "cs": {"Program.cs": "decimal amountSek = 100m;\ndecimal amountEur = amountSek;\nConsole.WriteLine(amountEur);\n"},
        "ts": {"main.ts": "const amountSek: number = 100;\nconst amountEur: number = amountSek;\nconsole.log(amountEur);\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc main() { amountSek := 100.0; amountEur := amountSek; fmt.Println(amountEur) }\n"},
        "rs": {"main.rs": "fn main() { let amount_sek: f64 = 100.0; let amount_eur: f64 = amount_sek; println!(\"{}\", amount_eur); }\n"},
    })

    # ===== CATEGORY 3: CHANGED SIGNATURE (S1-S5) =====
    s1_setup, s1_mut = make_py_dep(
        "def fee(x: float) -> float:\n    return x * 1.1\n",
        "def fee(x: float, zone: str) -> float:\n    return x * 1.1\n",
    )
    cases.append({
        "id": "S1_extra_required_param",
        "category": "changed_signature",
        "is_control": False,
        "description": "Dependency adds a new required parameter (arity change)",
        "b": ("use py:depmod as dep\nlet v: Float = dep.fee(10.0)\nprint v\n", s1_setup, s1_mut),
        "py": {
            "depmod.py": "def fee(x: float, zone: str) -> float:\n    return x * 1.1\n",
            "main.py": "import depmod\nprint(depmod.fee(10.0))\n",
        },
        "cs": {
            "Dep.cs": "public static class Dep { public static double Fee(double x, string zone) => x * 1.1; }\n",
            "Program.cs": "Console.WriteLine(Dep.Fee(10.0));\n",
        },
        "ts": {
            "dep.ts": "export function fee(x: number, zone: string): number { return x * 1.1; }\n",
            "main.ts": "import { fee } from './dep';\nconsole.log(fee(10.0));\n",
        },
        "go": {
            "dep.go": "package main\nfunc fee(x float64, zone string) float64 { return x * 1.1 }\n",
            "main.go": "package main\nimport \"fmt\"\nfunc main() { fmt.Println(fee(10.0)) }\n",
        },
        "rs": {
            "main.rs": "fn fee(x: f64, _zone: &str) -> f64 { x * 1.1 }\nfn main() { println!(\"{}\", fee(10.0)); }\n",
        },
    })

    s2_setup, s2_mut = make_py_dep(
        "def lookup(k: str) -> str:\n    return k\n",
        "def lookup(k: str) -> str | None:\n    return None\n",
    )
    cases.append({
        "id": "S2_return_becomes_nullable",
        "category": "changed_signature",
        "is_control": False,
        "description": "Dependency return type becomes nullable/Optional",
        "b": ("use py:depmod as dep\nlet s: Text = dep.lookup(\"a\")\nprint s\n", s2_setup, s2_mut),
        "py": {
            "depmod.py": "def lookup(k: str) -> str | None:\n    return None\n",
            "main.py": "import depmod\ns: str = depmod.lookup('a')\nprint(s)\n",
        },
        "cs": {
            "Dep.cs": "public static class Dep { public static string? Lookup(string k) => null; }\n",
            "Program.cs": "string s = Dep.Lookup(\"a\");\nConsole.WriteLine(s);\n",
        },
        "ts": {
            "dep.ts": "export function lookup(k: string): string | null { return null; }\n",
            "main.ts": "import { lookup } from './dep';\nconst s: string = lookup('a');\nconsole.log(s);\n",
        },
        "go": {
            "dep.go": "package main\nfunc lookup(k string) *string { return nil }\n",
            "main.go": "package main\nimport \"fmt\"\nfunc main() { var s string = lookup(\"a\"); fmt.Println(s) }\n",
        },
        "rs": {
            "main.rs": "fn lookup(_k: &str) -> Option<String> { None }\nfn main() { let s: String = lookup(\"a\"); println!(\"{}\", s); }\n",
        },
    })

    s3_setup, s3_mut = make_py_dep(
        "def normalize(n: int) -> int:\n    return n + 1\n",
        "def normalize(n: str) -> int:\n    return len(n)\n",
    )
    cases.append({
        "id": "S3_param_type_changed",
        "category": "changed_signature",
        "is_control": False,
        "description": "Dependency parameter type changes from Int to Text",
        "b": ("use py:depmod as dep\nlet v: Int = dep.normalize(5)\nprint v\n", s3_setup, s3_mut),
        "py": {
            "depmod.py": "def normalize(n: str) -> int:\n    return len(n)\n",
            "main.py": "import depmod\nprint(depmod.normalize(5))\n",
        },
        "cs": {
            "Dep.cs": "public static class Dep { public static int Normalize(string n) => n.Length; }\n",
            "Program.cs": "Console.WriteLine(Dep.Normalize(5));\n",
        },
        "ts": {
            "dep.ts": "export function normalize(n: string): number { return n.length; }\n",
            "main.ts": "import { normalize } from './dep';\nconsole.log(normalize(5));\n",
        },
        "go": {
            "dep.go": "package main\nfunc normalize(n string) int { return len(n) }\n",
            "main.go": "package main\nimport \"fmt\"\nfunc main() { fmt.Println(normalize(5)) }\n",
        },
        "rs": {
            "main.rs": "fn normalize(n: &str) -> usize { n.len() }\nfn main() { println!(\"{}\", normalize(5)); }\n",
        },
    })

    s4_setup, s4_mut = make_js_dep(
        "exports.normalizeCode = (s) => s.trim().toUpperCase();\n",
        "exports.canonicalCode = (s) => s.trim().toUpperCase();\n",
    )
    cases.append({
        "id": "S4_export_removed",
        "category": "changed_signature",
        "is_control": False,
        "description": "External npm/library export renamed or removed",
        "b": ('use js:"dep-pkg" as pkg\nforeign pkg.normalizeCode(Text) -> Text\nprint pkg.normalizeCode("ab")\n', s4_setup, s4_mut),
        "py": {
            "depmod.py": "def canonical_code(s: str) -> str:\n    return s.strip().upper()\n",
            "main.py": "import depmod\nprint(depmod.normalize_code('ab'))\n",
        },
        "cs": {
            "Dep.cs": "public static class Dep { public static string CanonicalCode(string s) => s.Trim().ToUpperInvariant(); }\n",
            "Program.cs": "Console.WriteLine(Dep.NormalizeCode(\"ab\"));\n",
        },
        "ts": {
            "dep.ts": "export function canonicalCode(s: string): string { return s.trim().toUpperCase(); }\n",
            "main.ts": "import { normalizeCode } from './dep';\nconsole.log(normalizeCode('ab'));\n",
        },
        "go": {
            "dep.go": "package main\nimport \"strings\"\nfunc canonicalCode(s string) string { return strings.ToUpper(strings.TrimSpace(s)) }\n",
            "main.go": "package main\nimport \"fmt\"\nfunc main() { fmt.Println(normalizeCode(\"ab\")) }\n",
        },
        "rs": {
            "main.rs": "fn canonical_code(s: &str) -> String { s.trim().to_uppercase() }\nfn main() { println!(\"{}\", normalize_code(\"ab\")); }\n",
        },
    })

    s5_setup, s5_mut = make_js_dep(
        "exports.score = (x) => x * 2;\n",
        "exports.score = (x, mode) => mode === 'fast' ? x * 2 : x * 3;\n",
    )
    cases.append({
        "id": "S5_unannotated_arity_drift",
        "category": "changed_signature",
        "is_control": False,
        "description": "Unannotated/JS/ambient-typed dependency changes parameter arity without updating ambient stub",
        "b": ('use js:"dep-pkg" as pkg\nforeign pkg.score(Int) -> Int\nprint pkg.score(5)\n', s5_setup, s5_mut),
        # Realistic Python untyped third-party dep + stale/missing annotations
        "py": {
            "depmod.py": "def score(x, mode):\n    return x * 2 if mode == 'fast' else x * 3\n",
            "main.py": "import depmod  # type: ignore[import-untyped]\nval: int = depmod.score(5)\nprint(val)\n",
        },
        # Realistic TS: JS package updated arity while ambient .d.ts remained stale
        "ts": {
            "dep.d.ts": "export function score(x: number): number;\n",
            "dep.js": "exports.score = (x, mode) => mode === 'fast' ? x * 2 : x * 3;\n",
            "main.ts": "import { score } from './dep';\nconsole.log(score(5));\n",
        },
        # C#, Go, Rust compile directly against source/metadata -> catch arity change!
        "cs": {
            "Dep.cs": "public static class Dep { public static int Score(int x, string mode) => mode == \"fast\" ? x * 2 : x * 3; }\n",
            "Program.cs": "Console.WriteLine(Dep.Score(5));\n",
        },
        "go": {
            "dep.go": "package main\nfunc score(x int, mode string) int { if mode == \"fast\" { return x * 2 }; return x * 3 }\n",
            "main.go": "package main\nimport \"fmt\"\nfunc main() { fmt.Println(score(5)) }\n",
        },
        "rs": {
            "main.rs": "fn score(x: i64, mode: &str) -> i64 { if mode == \"fast\" { x * 2 } else { x * 3 } }\nfn main() { println!(\"{}\", score(5)); }\n",
        },
    })

    # ===== CATEGORY 4: SILENTLY CHANGED LIBRARY BEHAVIOR (B1-B5) =====
    b1_setup, b1_mut = make_py_dep(
        "def round_fee(x: float) -> float:\n    return float(round(x))\n",
        "import math\ndef round_fee(x: float) -> float:\n    return float(math.floor(x + 0.5))\n",
    )
    cases.append({
        "id": "B1_rounding_mode_flip",
        "category": "silent_behavior_drift",
        "is_control": False,
        "description": "Dependency silently switches half-to-even rounding to half-up with identical type signature",
        "b": ("use py:depmod as dep\nprobe dep.round_fee(2.5) == 2.0\nprint dep.round_fee(2.5)\n", b1_setup, b1_mut),
        "py": {
            "depmod.py": "import math\ndef round_fee(x: float) -> float:\n    return float(math.floor(x + 0.5))\n",
            "main.py": "import depmod\nprint(depmod.round_fee(2.5))\n",
        },
        "cs": {
            "Dep.cs": "public static class Dep { public static double RoundFee(double x) => Math.Floor(x + 0.5); }\n",
            "Program.cs": "Console.WriteLine(Dep.RoundFee(2.5));\n",
        },
        "ts": {
            "dep.ts": "export function roundFee(x: number): number { return Math.floor(x + 0.5); }\n",
            "main.ts": "import { roundFee } from './dep';\nconsole.log(roundFee(2.5));\n",
        },
        "go": {
            "dep.go": "package main\nimport \"math\"\nfunc roundFee(x float64) float64 { return math.Floor(x + 0.5) }\n",
            "main.go": "package main\nimport \"fmt\"\nfunc main() { fmt.Println(roundFee(2.5)) }\n",
        },
        "rs": {
            "main.rs": "fn round_fee(x: f64) -> f64 { (x + 0.5).floor() }\nfn main() { println!(\"{}\", round_fee(2.5)); }\n",
        },
    })

    b2_setup, b2_mut = make_js_dep(
        "exports.matchesRelease = (ver, rng) => !ver.includes('-') && ver.startsWith(rng);\n",
        "exports.matchesRelease = (ver, rng) => ver.startsWith(rng);\n",
    )
    cases.append({
        "id": "B2_semver_prerelease_drift",
        "category": "silent_behavior_drift",
        "is_control": False,
        "description": "Dependency silently starts admitting prerelease tags with identical (Text, Text)->Bool signature",
        "b": ('use js:"dep-pkg" as pkg\nforeign pkg.matchesRelease(Text, Text) -> Bool\nprobe pkg.matchesRelease("1.2.3-rc.1", "1.") == false\nprint pkg.matchesRelease("1.2.3", "1.")\n', b2_setup, b2_mut),
        "py": {
            "depmod.py": "def matches_release(ver: str, rng: str) -> bool:\n    return ver.startswith(rng)\n",
            "main.py": "import depmod\nprint(depmod.matches_release('1.2.3-rc.1', '1.'))\n",
        },
        "cs": {
            "Dep.cs": "public static class Dep { public static bool MatchesRelease(string v, string r) => v.StartsWith(r); }\n",
            "Program.cs": "Console.WriteLine(Dep.MatchesRelease(\"1.2.3-rc.1\", \"1.\"));\n",
        },
        "ts": {
            "dep.ts": "export function matchesRelease(v: string, r: string): boolean { return v.startsWith(r); }\n",
            "main.ts": "import { matchesRelease } from './dep';\nconsole.log(matchesRelease('1.2.3-rc.1', '1.'));\n",
        },
        "go": {
            "dep.go": "package main\nimport \"strings\"\nfunc matchesRelease(v, r string) bool { return strings.HasPrefix(v, r) }\n",
            "main.go": "package main\nimport \"fmt\"\nfunc main() { fmt.Println(matchesRelease(\"1.2.3-rc.1\", \"1.\")) }\n",
        },
        "rs": {
            "main.rs": "fn matches_release(v: &str, r: &str) -> bool { v.starts_with(r) }\nfn main() { println!(\"{}\", matches_release(\"1.2.3-rc.1\", \"1.\")); }\n",
        },
    })

    b3_setup, b3_mut = make_py_dep(
        "def vat_rate(code: str) -> float:\n    return 0.25 if code == 'SE' else 0.19\n",
        "def vat_rate(code: str) -> float:\n    return 0.24 if code == 'SE' else 0.19\n",
    )
    cases.append({
        "id": "B3_tax_rate_drift",
        "category": "silent_behavior_drift",
        "is_control": False,
        "description": "Dependency silently changes VAT lookup table value with identical (Text)->Float signature",
        "b": ('use py:depmod as dep\nprobe dep.vat_rate("SE") == 0.25\nprint dep.vat_rate("SE")\n', b3_setup, b3_mut),
        "py": {
            "depmod.py": "def vat_rate(code: str) -> float:\n    return 0.24 if code == 'SE' else 0.19\n",
            "main.py": "import depmod\nprint(depmod.vat_rate('SE'))\n",
        },
        "cs": {
            "Dep.cs": "public static class Dep { public static double VatRate(string c) => c == \"SE\" ? 0.24 : 0.19; }\n",
            "Program.cs": "Console.WriteLine(Dep.VatRate(\"SE\"));\n",
        },
        "ts": {
            "dep.ts": "export function vatRate(c: string): number { return c === 'SE' ? 0.24 : 0.19; }\n",
            "main.ts": "import { vatRate } from './dep';\nconsole.log(vatRate('SE'));\n",
        },
        "go": {
            "dep.go": "package main\nfunc vatRate(c string) float64 { if c == \"SE\" { return 0.24 }; return 0.19 }\n",
            "main.go": "package main\nimport \"fmt\"\nfunc main() { fmt.Println(vatRate(\"SE\")) }\n",
        },
        "rs": {
            "main.rs": "fn vat_rate(c: &str) -> f64 { if c == \"SE\" { 0.24 } else { 0.19 } }\nfn main() { println!(\"{}\", vat_rate(\"SE\")); }\n",
        },
    })

    b4_setup, b4_mut = make_py_dep(
        "def bucket(n: int, size: int) -> int:\n    return n % size\n",
        "def bucket(n: int, size: int) -> int:\n    return n - int(n / size) * size\n",
    )
    cases.append({
        "id": "B4_negative_mod_drift",
        "category": "silent_behavior_drift",
        "is_control": False,
        "description": "Dependency silently changes negative modulo from non-negative to signed truncated remainder",
        "b": ("use py:depmod as dep\nprint dep.bucket(-5, 4)\n", b4_setup, b4_mut),
        "py": {
            "depmod.py": "def bucket(n: int, size: int) -> int:\n    return n - int(n / size) * size\n",
            "main.py": "import depmod\nprint(depmod.bucket(-5, 4))\n",
        },
        "cs": {
            "Dep.cs": "public static class Dep { public static int Bucket(int n, int s) => n % s; }\n",
            "Program.cs": "Console.WriteLine(Dep.Bucket(-5, 4));\n",
        },
        "ts": {
            "dep.ts": "export function bucket(n: number, s: number): number { return n % s; }\n",
            "main.ts": "import { bucket } from './dep';\nconsole.log(bucket(-5, 4));\n",
        },
        "go": {
            "dep.go": "package main\nfunc bucket(n, s int) int { return n % s }\n",
            "main.go": "package main\nimport \"fmt\"\nfunc main() { fmt.Println(bucket(-5, 4)) }\n",
        },
        "rs": {
            "main.rs": "fn bucket(n: i64, s: i64) -> i64 { n % s }\nfn main() { println!(\"{}\", bucket(-5, 4)); }\n",
        },
    })

    b5_setup, b5_mut = make_py_dep(
        "import re\ndef is_valid_tag(tag: str) -> bool:\n    return re.fullmatch(r'v[0-9]+', tag) is not None\n",
        "import re\ndef is_valid_tag(tag: str) -> bool:\n    return re.match(r'v[0-9]+', tag) is not None\n",
    )
    cases.append({
        "id": "B5_regex_anchor_drift",
        "category": "silent_behavior_drift",
        "is_control": False,
        "description": "Dependency silently weakens regex from fullmatch to prefix match with identical signature",
        "b": ('use py:depmod as dep\nprobe dep.is_valid_tag("v1-bad") == false\nprint dep.is_valid_tag("v1")\n', b5_setup, b5_mut),
        "py": {
            "depmod.py": "import re\ndef is_valid_tag(tag: str) -> bool:\n    return re.match(r'v[0-9]+', tag) is not None\n",
            "main.py": "import depmod\nprint(depmod.is_valid_tag('v1-bad'))\n",
        },
        "cs": {
            "Dep.cs": "using System.Text.RegularExpressions;\npublic static class Dep { public static bool IsValidTag(string t) => Regex.IsMatch(t, \"^v[0-9]+\"); }\n",
            "Program.cs": "Console.WriteLine(Dep.IsValidTag(\"v1-bad\"));\n",
        },
        "ts": {
            "dep.ts": "export function isValidTag(t: string): boolean { return /^v[0-9]+/.test(t); }\n",
            "main.ts": "import { isValidTag } from './dep';\nconsole.log(isValidTag('v1-bad'));\n",
        },
        "go": {
            "dep.go": "package main\nimport \"regexp\"\nfunc isValidTag(t string) bool { ok, _ := regexp.MatchString(`^v[0-9]+`, t); return ok }\n",
            "main.go": "package main\nimport \"fmt\"\nfunc main() { fmt.Println(isValidTag(\"v1-bad\")) }\n",
        },
        "rs": {
            "main.rs": "fn is_valid_tag(t: &str) -> bool { t.starts_with('v') }\nfn main() { println!(\"{}\", is_valid_tag(\"v1-bad\")); }\n",
        },
    })

    # ===== CATEGORY 5: SEMANTIC DIFFERENCES BETWEEN ECOSYSTEMS (E1-E5) =====
    cases.append({
        "id": "E1_utf16_vs_codepoints",
        "category": "ecosystem_semantics",
        "is_control": False,
        "description": "UTF-16 code-unit length/distance (JS/C#) assumed to be Unicode codepoint count",
        "b": ('use js:"fastest-levenshtein" as lev\nforeign lev.distance(Text, Text) -> Int\nexpect lev.distance string_unit = codepoints\nprint lev.distance("😀", "")\n', None, None),
        "py": {"main.py": "def utf16_units(s: str) -> int:\n    return len(s.encode('utf-16-le')) // 2\ncodepoints: int = utf16_units('😀')\nprint(codepoints)\n"},
        "cs": {"Program.cs": "int codepoints = \"😀\".Length;\nConsole.WriteLine(codepoints);\n"},
        "ts": {"main.ts": "const codepoints: number = \"😀\".length;\nconsole.log(codepoints);\n"},
        "go": {"main.go": "package main\nimport (\"fmt\"; \"unicode/utf16\")\nfunc main() { codepoints := len(utf16.Encode([]rune(\"😀\"))); fmt.Println(codepoints) }\n"},
        "rs": {"main.rs": "fn main() { let codepoints: usize = \"😀\".encode_utf16().count(); println!(\"{}\", codepoints); }\n"},
    })

    cases.append({
        "id": "E2_utf8_bytes_vs_codepoints",
        "category": "ecosystem_semantics",
        "is_control": False,
        "description": "UTF-8 byte length (Go len / Rust .len()) assumed to be Unicode codepoint count",
        "b": ('use rs:std.str as rstr\nexpect rstr.len_bytes string_unit = codepoints\nprint rstr.len_bytes("😀")\n', None, None),
        "py": {"main.py": "codepoints: int = len('😀'.encode('utf-8'))\nprint(codepoints)\n"},
        "cs": {"Program.cs": "int codepoints = System.Text.Encoding.UTF8.GetByteCount(\"😀\");\nConsole.WriteLine(codepoints);\n"},
        "ts": {"main.ts": "const codepoints: number = Buffer.byteLength('😀', 'utf8');\nconsole.log(codepoints);\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc main() { codepoints := len(\"😀\"); fmt.Println(codepoints) }\n"},
        "rs": {"main.rs": "fn main() { let codepoints: usize = \"😀\".len(); println!(\"{}\", codepoints); }\n"},
    })

    cases.append({
        "id": "E3_rounding_half_away_vs_even",
        "category": "ecosystem_semantics",
        "is_control": False,
        "description": "Half-away-from-zero rounding (Go/Rust) assumed to match banker's half-even (Python/.NET)",
        "b": ("use go:math as gmath\nexpect gmath.Round rounding = half_even\nprint gmath.Round(2.5)\n", None, None),
        "py": {"main.py": "import math\ndef round_bankers(x: float) -> float:\n    return math.floor(x + 0.5)\nprint(round_bankers(2.5))\n"},
        "cs": {"Program.cs": "double r = Math.Round(2.5, MidpointRounding.AwayFromZero);\nConsole.WriteLine(r);\n"},
        "ts": {"main.ts": "const r: number = Math.round(2.5);\nconsole.log(r);\n"},
        "go": {"main.go": "package main\nimport (\"fmt\"; \"math\")\nfunc main() { fmt.Println(math.Round(2.5)) }\n"},
        "rs": {"main.rs": "fn main() { println!(\"{}\", 2.5_f64.round()); }\n"},
    })

    cases.append({
        "id": "E4_remainder_trunc_vs_floor",
        "category": "ecosystem_semantics",
        "is_control": False,
        "description": "Truncated negative remainder (C#/TS/Go/Rust %) assumed to match floored/Euclidean non-negative remainder",
        "b": ("use rs:std.i64 as ri\nexpect ri.rem_trunc remainder = euclid\nprint ri.rem_trunc(-5, 4)\n", None, None),
        "py": {"main.py": "import math\nrem: float = math.fmod(-5, 4)\nprint(rem)\n"},
        "cs": {"Program.cs": "int rem = -5 % 4;\nConsole.WriteLine(rem);\n"},
        "ts": {"main.ts": "const rem: number = -5 % 4;\nconsole.log(rem);\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc main() { rem := -5 % 4; fmt.Println(rem) }\n"},
        "rs": {"main.rs": "fn main() { let rem: i64 = -5 % 4; println!(\"{}\", rem); }\n"},
    })

    cases.append({
        "id": "E5_js_safe_int_overflow",
        "category": "ecosystem_semantics",
        "is_control": False,
        "description": "Integer > 2^53 - 1 passed into JavaScript Number boundary (silent precision loss)",
        "b": ('use js:"dep-pkg" as pkg\nforeign pkg.echo(Int) -> Int\nprint pkg.echo(9007199254740993)\n', None, None),
        "py": {"main.py": "x: float = float(9007199254740993)\nprint(x)\n"},
        "cs": {"Program.cs": "double x = 9007199254740993L;\nConsole.WriteLine(x);\n"},
        "ts": {"main.ts": "const x: number = 9007199254740993;\nconsole.log(x);\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc main() { x := float64(9007199254740993); fmt.Println(x) }\n"},
        "rs": {"main.rs": "fn main() { let x: f64 = 9007199254740993_i64 as f64; println!(\"{}\", x); }\n"},
    })

    # ===== 5 CLEAN NEGATIVE CONTROLS (MUST BE ACCEPTED BY ALL 6 LANGUAGES) =====
    cases.append({
        "id": "CTRL_U_valid_unit_conversion",
        "category": "control",
        "is_control": True,
        "description": "Valid unit conversion km -> m before addition",
        "b": ("unit m\nunit km = 1000 m\nfn total(a_m: Float[m], b_km: Float[km]) -> Float[m] pure = a_m + (b_km to m)\nprint scalar(total(500.0 as m, 2.0 as km))\n", None, None),
        "py": {"main.py": "def total(a_m: float, b_km: float) -> float:\n    return a_m + b_km * 1000.0\nprint(total(500.0, 2.0))\n"},
        "cs": {"Program.cs": "static double Total(double aM, double bKm) => aM + bKm * 1000.0;\nConsole.WriteLine(Total(500.0, 2.0));\n"},
        "ts": {"main.ts": "function total(aM: number, bKm: number): number { return aM + bKm * 1000.0; }\nconsole.log(total(500.0, 2.0));\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc total(aM float64, bKm float64) float64 { return aM + bKm*1000.0 }\nfunc main() { fmt.Println(total(500.0, 2.0)) }\n"},
        "rs": {"main.rs": "fn total(a_m: f64, b_km: f64) -> f64 { a_m + b_km * 1000.0 }\nfn main() { println!(\"{}\", total(500.0, 2.0)); }\n"},
    })

    cases.append({
        "id": "CTRL_C_valid_explicit_fx",
        "category": "control",
        "is_control": True,
        "description": "Valid explicit FX conversion EUR -> SEK before addition",
        "b": ("currency SEK, EUR\nfn eur_to_sek(x: Float[EUR], rate: Float) -> Float[SEK] pure = (scalar(x) * rate) as SEK\nfn invoice(item: Float[SEK], ship: Float[EUR], rate: Float) -> Float[SEK] pure = item + eur_to_sek(ship, rate)\nprint scalar(invoice(100.0 as SEK, 10.0 as EUR, 11.5))\n", None, None),
        "py": {"main.py": "def invoice(item_sek: float, ship_eur: float, rate: float) -> float:\n    return item_sek + ship_eur * rate\nprint(invoice(100.0, 10.0, 11.5))\n"},
        "cs": {"Program.cs": "static decimal Invoice(decimal s, decimal e, decimal r) => s + e * r;\nConsole.WriteLine(Invoice(100m, 10m, 11.5m));\n"},
        "ts": {"main.ts": "function invoice(s: number, e: number, r: number): number { return s + e * r; }\nconsole.log(invoice(100, 10, 11.5));\n"},
        "go": {"main.go": "package main\nimport \"fmt\"\nfunc invoice(s, e, r float64) float64 { return s + e*r }\nfunc main() { fmt.Println(invoice(100, 10, 11.5)) }\n"},
        "rs": {"main.rs": "fn invoice(s: f64, e: f64, r: f64) -> f64 { s + e * r }\nfn main() { println!(\"{}\", invoice(100.0, 10.0, 11.5)); }\n"},
    })

    cs_setup, cs_mut = make_py_dep(
        "def fee(x: float) -> float:\n    return x * 1.1\n",
        "def fee(x: float) -> float:\n    return x * 1.1\n",
    )
    cases.append({
        "id": "CTRL_S_stable_signature",
        "category": "control",
        "is_control": True,
        "description": "Stable dependency signature",
        "b": ("use py:depmod as dep\nlet v: Float = dep.fee(10.0)\nprint v\n", cs_setup, cs_mut),
        "py": {"depmod.py": "def fee(x: float) -> float:\n    return x * 1.1\n", "main.py": "import depmod\nprint(depmod.fee(10.0))\n"},
        "cs": {"Dep.cs": "public static class Dep { public static double Fee(double x) => x * 1.1; }\n", "Program.cs": "Console.WriteLine(Dep.Fee(10.0));\n"},
        "ts": {"dep.ts": "export function fee(x: number): number { return x * 1.1; }\n", "main.ts": "import { fee } from './dep';\nconsole.log(fee(10.0));\n"},
        "go": {"dep.go": "package main\nfunc fee(x float64) float64 { return x * 1.1 }\n", "main.go": "package main\nimport \"fmt\"\nfunc main() { fmt.Println(fee(10.0)) }\n"},
        "rs": {"main.rs": "fn fee(x: f64) -> f64 { x * 1.1 }\nfn main() { println!(\"{}\", fee(10.0)); }\n"},
    })

    cb_setup, cb_mut = make_py_dep(
        "def round_fee(x: float) -> float:\n    return float(round(x))\n",
        "def round_fee(x: float) -> float:\n    return float(round(x))\n",
    )
    cases.append({
        "id": "CTRL_B_stable_behavior",
        "category": "control",
        "is_control": True,
        "description": "Stable dependency behavior verified by probe & lockfile",
        "b": ("use py:depmod as dep\nprobe dep.round_fee(2.5) == 2.0\nprint dep.round_fee(2.5)\n", cb_setup, cb_mut),
        "py": {"depmod.py": "def round_fee(x: float) -> float:\n    return float(round(x))\n", "main.py": "import depmod\nprint(depmod.round_fee(2.5))\n"},
        "cs": {"Dep.cs": "public static class Dep { public static double RoundFee(double x) => Math.Round(x); }\n", "Program.cs": "Console.WriteLine(Dep.RoundFee(2.5));\n"},
        "ts": {"dep.ts": "export function roundFee(x: number): number { return Math.round(x); }\n", "main.ts": "import { roundFee } from './dep';\nconsole.log(roundFee(2.5));\n"},
        "go": {"dep.go": "package main\nimport \"math\"\nfunc roundFee(x float64) float64 { return math.RoundToEven(x) }\n", "main.go": "package main\nimport \"fmt\"\nfunc main() { fmt.Println(roundFee(2.5)) }\n"},
        "rs": {"main.rs": "fn round_fee(x: f64) -> f64 { x.round_ties_even() }\nfn main() { println!(\"{}\", round_fee(2.5)); }\n"},
    })

    cases.append({
        "id": "CTRL_E_matching_semantics",
        "category": "control",
        "is_control": True,
        "description": "Explicitly matching cross-ecosystem semantics (Go RoundToEven + Rust len_chars)",
        "b": ("use go:math as gmath\nuse rs:std.str as rstr\nexpect gmath.RoundToEven rounding = half_even\nexpect rstr.len_chars string_unit = codepoints\nprint gmath.RoundToEven(2.5)\nprint rstr.len_chars(\"😀\")\n", None, None),
        "py": {"main.py": "print(round(2.5), len('😀'))\n"},
        "cs": {"Program.cs": "Console.WriteLine($\"{Math.Round(2.5)} {\"😀\".EnumerateRunes().Count()}\");\n"},
        "ts": {"main.ts": "console.log(Array.from('😀').length);\n"},
        "go": {"main.go": "package main\nimport (\"fmt\"; \"math\"; \"unicode/utf8\")\nfunc main() { fmt.Println(math.RoundToEven(2.5), utf8.RuneCountInString(\"😀\")) }\n"},
        "rs": {"main.rs": "fn main() { println!(\"{} {}\", 2.5_f64.round_ties_even(), \"😀\".chars().count()); }\n"},
    })

    return cases


def main() -> int:
    cases = build_cases()
    script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    prereg_sha = hashlib.sha256((STUDY_DIR / "PREREGISTRATION.md").read_bytes()).hexdigest()

    langs = ["B", "Python", "C#", "TypeScript", "Go", "Rust"]
    rows = []

    with tempfile.TemporaryDirectory(prefix="b_false_friends_") as tmp:
        tmp_root = Path(tmp)
        for case in cases:
            cdir = tmp_root / case["id"]
            cdir.mkdir()
            b_src, b_setup, b_mut = case["b"]
            res = {}
            res["B"] = check_b(cdir, b_src, lock_setup=b_setup, mutate_after_lock=b_mut)
            res["Python"] = check_python(cdir, case["py"])
            res["C#"] = check_csharp(cdir, case["cs"])
            res["TypeScript"] = check_typescript(cdir, case["ts"])
            res["Go"] = check_go(cdir, case["go"])
            res["Rust"] = check_rust(cdir, case["rs"])

            row = {
                "id": case["id"],
                "category": case["category"],
                "is_control": case["is_control"],
                "description": case["description"],
                "stopped": {lang: res[lang][0] for lang in langs},
                "diagnostics": {lang: res[lang][1][:300] for lang in langs},
            }
            rows.append(row)
            status = " ".join(f"{l}={'STOP' if res[l][0] else 'PASS'}" for l in langs)
            print(f"{case['id']:32s} [{case['category']:21s}] {status}")

    faults = [r for r in rows if not r["is_control"]]
    controls = [r for r in rows if r["is_control"]]

    summary = {}
    for lang in langs:
        stopped_total = sum(1 for r in faults if r["stopped"][lang])
        false_pos = sum(1 for r in controls if r["stopped"][lang])
        by_cat = {}
        for cat in ("wrong_unit", "wrong_currency", "changed_signature", "silent_behavior_drift", "ecosystem_semantics"):
            cat_rows = [r for r in faults if r["category"] == cat]
            by_cat[cat] = f"{sum(1 for r in cat_rows if r['stopped'][lang])}/{len(cat_rows)}"
        summary[lang] = {
            "stopped": stopped_total,
            "total_faults": len(faults),
            "stop_rate_pct": round(100.0 * stopped_total / len(faults), 1),
            "control_false_positives": false_pos,
            "total_controls": len(controls),
            "by_category": by_cat,
        }

    report = {
        "study": "false-friends-before-execution",
        "script_sha256": script_sha,
        "preregistration_sha256": prereg_sha,
        "summary": summary,
        "cases": rows,
    }
    out_path = STUDY_DIR / "results.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("\n=== SUMMARY (Faults Stopped Before Execution) ===")
    for lang in langs:
        s = summary[lang]
        print(f"{lang:12s}: {s['stopped']:2d}/{s['total_faults']} ({s['stop_rate_pct']:5.1f}%)  "
              f"false_pos={s['control_false_positives']}/{s['total_controls']}  {s['by_category']}")

    b_rate = summary["B"]["stop_rate_pct"]
    best_sibling = max(summary[l]["stopped"] for l in langs if l != "B")
    ok = (b_rate >= 80.0 and summary["B"]["stopped"] > best_sibling and summary["B"]["control_false_positives"] == 0)
    print(f"\nCondition 4 verdict: {'PASS' if ok else 'FAIL'} (B={summary['B']['stopped']}/{len(faults)} [{b_rate}%], best sibling={best_sibling}/{len(faults)})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
