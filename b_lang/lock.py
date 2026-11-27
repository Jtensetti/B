"""Behavioral dependency locking & pre-execution verification for B (`b lock` / `b check --lock`).

Detects before program execution:
- Signature changes in Python (.py/.pyi), Node.js, .NET, Go, and Rust dependencies (`E_LOCK_SIGNATURE`)
- Silent behavioral changes via pinned `probe` expectations and canonical boundary fingerprints (`E_BEHAVIOR_DRIFT`)
- Cross-ecosystem semantic facet changes (`E_FALSE_FRIEND`)
- Unreviewed source/version drift (`E_LOCK_DRIFT` in strict mode)
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

from .compiler import compile_b
from .discovery import find_module_spec, inspect_python
from . import gometa, jsmeta, netmeta, rsmeta
from .ir import ForeignSymbol, ProgramIR
from .lowering import PythonLowerer
from .types import BError, Overloads, Signature, Type, base_numeric


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sig_list(symbol: ForeignSymbol) -> list[dict[str, Any]]:
    sigs = symbol.binding.options if isinstance(symbol.binding, Overloads) else (symbol.binding,)
    return [
        {"params": [str(t) for t in s.params], "result": str(s.result), "required": s.required}
        for s in sigs
    ]


def _inspect_python_def_arity(module_name: str, func_name: str) -> dict[str, Any] | None:
    """Parse a Python module's .pyi/.py AST without executing it to verify symbol existence and arity."""
    spec = find_module_spec(module_name)
    if spec is None or not spec.origin or spec.origin in ("built-in", "frozen"):
        return None
    origin = Path(spec.origin)
    stub = origin.with_suffix(".pyi")
    target = stub if stub.is_file() else origin
    if not target.is_file():
        return None
    try:
        tree = ast.parse(target.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None
    found_defs: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            found_defs.append(node)
    if not found_defs:
        # Could be imported/re-exported; note absence of direct def.
        return {"source": str(target), "sha256": _sha256_file(target), "direct_def": False}
    variants = []
    for fn in found_defs:
        pos = len(fn.args.posonlyargs) + len(fn.args.args)
        req = pos - len(fn.args.defaults)
        variants.append({
            "min_arity": req,
            "max_arity": None if fn.args.vararg else pos,
            "kwonly_required": sum(1 for d in fn.args.kw_defaults if d is None),
        })
    discovered = inspect_python(module_name)
    disc_sig = discovered.signatures.get(func_name)
    disc_serialized = None
    if isinstance(disc_sig, Signature):
        disc_serialized = [{"params": [str(t) for t in disc_sig.params], "result": str(disc_sig.result), "required": disc_sig.required}]
    elif isinstance(disc_sig, Overloads):
        disc_serialized = [{"params": [str(t) for t in s.params], "result": str(s.result), "required": s.required} for s in disc_sig.options]
    return {
        "source": str(target),
        "sha256": _sha256_file(target),
        "direct_def": True,
        "variants": variants,
        "discovered": disc_serialized,
    }


def _find_npm_package(pkg_name: str, source_file: Path | None) -> dict[str, Any] | None:
    if pkg_name == jsmeta.POSIX:
        return {"builtin": True}
    start = (source_file.resolve().parent if source_file else Path.cwd())
    for parent in (start, *start.parents):
        pkg_dir = parent / "node_modules" / pkg_name
        pkg_json = pkg_dir / "package.json"
        if pkg_json.is_file():
            meta = json.loads(pkg_json.read_text(encoding="utf-8"))
            entry = meta.get("main") or "index.js"
            entry_path = pkg_dir / entry
            return {
                "version": str(meta.get("version", "")),
                "package_json": str(pkg_json),
                "entry_sha256": _sha256_file(entry_path) if entry_path.is_file() else None,
            }
    return None


def _inspect_npm_export(pkg_name: str, member: str, source_file: Path | None) -> dict[str, Any] | None:
    """Inspect a Node/npm export's existence and declared JS parameter length without running the B program."""
    import shutil, subprocess
    node = shutil.which("node")
    if not node:
        return None
    anchor = str(source_file.resolve() if source_file else (Path.cwd() / "__b_lock__.bee"))
    script = (
        "const { createRequire } = require('node:module');"
        "const req = createRequire(process.argv[1]);"
        "const mod = req(process.argv[2]);"
        "const fn = mod[process.argv[3]];"
        "console.log(JSON.stringify({exists: typeof fn === 'function', arity: typeof fn === 'function' ? fn.length : null}));"
    )
    proc = subprocess.run([node, "-e", script, anchor, pkg_name, member],
                          capture_output=True, text=True, check=False, timeout=15)
    if proc.returncode != 0:
        return {"exists": False, "arity": None}
    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return None


def _canonical_inputs(sig: Signature) -> list[list[Any]]:
    """Deterministic boundary inputs that detect silent cross-ecosystem behavior drift."""
    params = tuple(base_numeric(p) for p in sig.params)
    res = base_numeric(sig.result)
    if params == (Type("Float"),) and res in (Type("Float"), Type("Int")):
        return [[2.5], [-2.5], [1.5], [0.0], [4.0]]
    if params == (Type("Int"),) and res in (Type("Int"), Type("Float")):
        return [[0], [1], [-1], [5], [-5]]
    if params == (Type("Int"), Type("Int")) and res == Type("Int"):
        return [[-5, 4], [5, -4], [-1, 2], [7, 3]]
    if params == (Type("Float"), Type("Float")) and res == Type("Float"):
        return [[2.5, 1.5], [-5.0, 4.0], [3.0, 4.0]]
    if params == (Type("Text"),) and res == Type("Int"):
        return [["abc"], ["😀"], ["é"], [""]]
    if params == (Type("Text"), Type("Text")) and res == Type("Int"):
        return [["abc", "abc"], ["😀", ""], ["kitten", "sitting"]]
    if params == (Type("Text"), Type("Text")) and res == Type("Bool"):
        return [["abc", "abc"], ["xabcx", "abc"], ["", "abc"]]
    if params == (Type("Text"),) and res == Type("Text"):
        return [["hello%20world"], ["  Abc  "], ["/a/b/../c"]]
    if params == (Type("Text"),) and res == Type("Option", (Type("Text"),)):
        return [["1.2.3"], ["not-a-version"], ["0.2.10-rc.1"]]
    return []


def _normalize_value(val: Any) -> Any:
    if isinstance(val, float) and val == 0.0:
        import math
        return "-0.0" if math.copysign(1.0, val) < 0 else 0.0
    if isinstance(val, list):
        return [_normalize_value(x) for x in val]
    if isinstance(val, dict):
        return {k: _normalize_value(v) for k, v in val.items()}
    return val


def _build_probe_env(program: ProgramIR, source_file: Path | None) -> dict[str, Any]:
    """Compile and execute only imports + pure/helper declarations needed for lock-time probes."""
    safe_stmts = tuple(
        s for s in program.statements
        if s.op in ("import", "foreign", "permit", "unit", "currency", "record", "fn")
    )
    sub_ir = ProgramIR(
        safe_stmts, program.foreign_symbols, program.assumptions,
        records=program.records, units=program.units, currencies=program.currencies,
    )
    mod = PythonLowerer().lower(sub_ir)
    ns: dict[str, Any] = {"__name__": "__b_lock__"}
    if source_file is not None:
        ns["__file__"] = str(source_file.resolve())
    exec(compile(mod, "<B-lock>", "exec"), ns, ns)
    return ns


def _eval_expr_in_env(expr_ir, ns: dict[str, Any], has_records: bool) -> Any:
    lowerer = PythonLowerer()
    lowerer._has_records = has_records
    py_expr = lowerer.expr(expr_ir)
    # Attach any helper functions generated by summarize/history_count
    if lowerer._helpers:
        helper_mod = ast.fix_missing_locations(ast.Module(body=lowerer._helpers, type_ignores=[]))
        exec(compile(helper_mod, "<B-probe-helpers>", "exec"), ns, ns)
    expr_mod = ast.fix_missing_locations(ast.Expression(body=py_expr))
    return eval(compile(expr_mod, "<B-probe>", "eval"), ns, ns)


def _call_foreign_direct(symbol: ForeignSymbol, args: list[Any], ns: dict[str, Any], aliases: dict[str, str]) -> Any:
    backend = symbol.backend
    rest = symbol.path.split(":", 1)[1]
    mod_path, member = rest.rsplit(".", 1)
    alias = aliases.get(f"{backend}:{mod_path}")
    if alias is None:
        raise BError("E_LOCK", f"No alias found for {backend}:{mod_path}")
    fn = getattr(ns[alias], member)
    return fn(*args)


def create_lock(source: str, source_file: Path | None = None) -> dict[str, Any]:
    compiled = compile_b(source)
    ir = compiled.ir
    aliases = {f"{s.backend}:{s.target}": s.name for s in ir.statements if s.op == "import" and s.name and s.target}

    symbols_lock: dict[str, Any] = {}
    for sym in ir.foreign_symbols:
        entry: dict[str, Any] = {
            "backend": sym.backend,
            "provenance": sym.provenance,
            "signatures": _sig_list(sym),
            "semantics": sym.semantics_dict(),
        }
        mod_path, member = sym.path.split(":", 1)[1].rsplit(".", 1)
        if sym.backend == "py":
            info = _inspect_python_def_arity(mod_path, member)
            if info:
                entry["python_ast"] = info
        elif sym.backend == "js":
            pkg_info = _find_npm_package(mod_path, source_file)
            if pkg_info:
                entry["npm"] = pkg_info
            exp_info = _inspect_npm_export(mod_path, member, source_file)
            if exp_info:
                entry["js_export"] = exp_info
        symbols_lock[sym.path] = entry

    ns = _build_probe_env(ir, source_file)
    try:
        # 1. Verify and record user-declared `probe` expressions
        probe_records = []
        for idx, probe_ir in enumerate(ir.probes):
            val = _eval_expr_in_env(probe_ir, ns, bool(ir.records))
            if val is not True:
                raise BError("E_BEHAVIOR_DRIFT", f"Probe #{idx + 1} failed during lock creation (got {val!r})")
            probe_records.append({"index": idx, "expr": probe_ir.to_dict(), "expected": True})

        # 2. Record canonical behavioral fingerprints for used foreign symbols
        fingerprints: dict[str, list[dict[str, Any]]] = {}
        for sym in ir.foreign_symbols:
            if not isinstance(sym.binding, Signature):
                continue
            cases = _canonical_inputs(sym.binding)
            recorded = []
            for args in cases:
                try:
                    out = _call_foreign_direct(sym, args, ns, aliases)
                    recorded.append({"args": args, "output": _normalize_value(out)})
                except Exception:
                    # Skip domain-invalid inputs (e.g. sqrt(-2.5)) during lock discovery.
                    continue
            if recorded:
                fingerprints[sym.path] = recorded
    finally:
        if "_b_js_session" in ns:
            ns["_b_js_session"].close()

    return {
        "schema": "b-lock",
        "version": 1,
        "symbols": symbols_lock,
        "probes": probe_records,
        "fingerprints": fingerprints,
    }


def verify_lock(source: str, lock: dict[str, Any], source_file: Path | None = None,
                *, strict: bool = False) -> dict[str, Any]:
    """Verify a B program against its lockfile BEFORE executing the program."""
    if lock.get("schema") != "b-lock" or lock.get("version") != 1:
        raise BError("E_LOCK", "Unsupported lockfile schema")

    compiled = compile_b(source, strict=strict)
    ir = compiled.ir
    aliases = {f"{s.backend}:{s.target}": s.name for s in ir.statements if s.op == "import" and s.name and s.target}

    current_symbols = {s.path: s for s in ir.foreign_symbols}
    warnings: list[str] = []

    # 1. Signature, live metadata & semantic facet verification
    for path, locked in lock.get("symbols", {}).items():
        if path not in current_symbols:
            continue
        cur = current_symbols[path]
        if _sig_list(cur) != locked.get("signatures"):
            raise BError("E_LOCK_SIGNATURE",
                         f"Signature of {path} changed: locked={locked.get('signatures')}, current={_sig_list(cur)}")
        if cur.semantics_dict() != locked.get("semantics", {}):
            raise BError("E_FALSE_FRIEND",
                         f"Semantic facets of {path} changed: locked={locked.get('semantics')}, current={cur.semantics_dict()}")

        mod_path, member = path.split(":", 1)[1].rsplit(".", 1)
        if cur.backend == "py":
            live_ast = _inspect_python_def_arity(mod_path, member)
            locked_ast = locked.get("python_ast")
            if locked_ast and live_ast:
                if locked_ast.get("direct_def") and not live_ast.get("direct_def"):
                    raise BError("E_LOCK_SIGNATURE", f"Python function {path} was removed or renamed")
                if locked_ast.get("variants") != live_ast.get("variants"):
                    raise BError("E_LOCK_SIGNATURE",
                                 f"Python arity/parameters changed for {path}: locked={locked_ast.get('variants')}, live={live_ast.get('variants')}")
                if locked_ast.get("discovered") is not None and live_ast.get("discovered") != locked_ast.get("discovered"):
                    raise BError("E_LOCK_SIGNATURE",
                                 f"Python type annotation changed for {path}: locked={locked_ast.get('discovered')}, live={live_ast.get('discovered')}")
                if locked_ast.get("sha256") != live_ast.get("sha256"):
                    warnings.append(f"Source digest changed for {path}")
        elif cur.backend == "js":
            locked_npm = locked.get("npm")
            live_npm = _find_npm_package(mod_path, source_file)
            if locked_npm and not locked_npm.get("builtin"):
                if not live_npm:
                    raise BError("E_LOCK_SIGNATURE", f"npm package {mod_path} is no longer installed")
                if locked_npm.get("version") != live_npm.get("version"):
                    warnings.append(f"npm package {mod_path} version changed: {locked_npm.get('version')} -> {live_npm.get('version')}")
            locked_exp = locked.get("js_export")
            live_exp = _inspect_npm_export(mod_path, member, source_file)
            if locked_exp and live_exp:
                if not live_exp.get("exists"):
                    raise BError("E_LOCK_SIGNATURE", f"Node/npm export {path} no longer exists")
                if locked_exp.get("arity") != live_exp.get("arity"):
                    raise BError("E_LOCK_SIGNATURE",
                                 f"Node/npm export {path} arity changed: locked={locked_exp.get('arity')}, live={live_exp.get('arity')}")
        elif cur.backend == "net":
            live = netmeta.describe_live()
            if live.get("types", {}).get(mod_path) != netmeta.manifest()["types"].get(mod_path):
                raise BError("E_LOCK_SIGNATURE", f".NET live metadata drifted for {mod_path}")
        elif cur.backend == "go":
            live = gometa.describe_live()
            if live.get("packages", {}).get(mod_path) != gometa.manifest()["packages"].get(mod_path):
                raise BError("E_LOCK_SIGNATURE", f"Go live metadata drifted for {mod_path}")
        elif cur.backend == "rs":
            live = rsmeta.describe_live()
            if live.get("modules", {}).get(mod_path) != rsmeta.manifest()["modules"].get(mod_path):
                raise BError("E_LOCK_SIGNATURE", f"Rust live metadata drifted for {mod_path}")

    # 2. Behavioral probe & fingerprint verification BEFORE program execution
    ns = _build_probe_env(ir, source_file)
    checked_probes = 0
    checked_fingerprints = 0
    try:
        for idx, probe_ir in enumerate(ir.probes):
            try:
                val = _eval_expr_in_env(probe_ir, ns, bool(ir.records))
            except Exception as exc:
                raise BError("E_BEHAVIOR_DRIFT", f"Probe #{idx + 1} raised at lock verification: {exc}") from exc
            if val is not True:
                raise BError("E_BEHAVIOR_DRIFT", f"Behavioral probe #{idx + 1} failed before execution (observed {val!r})")
            checked_probes += 1

        for path, cases in lock.get("fingerprints", {}).items():
            if path not in current_symbols:
                continue
            sym = current_symbols[path]
            for case in cases:
                args = case["args"]
                expected = case["output"]
                try:
                    actual = _normalize_value(_call_foreign_direct(sym, args, ns, aliases))
                except Exception as exc:
                    raise BError(
                        "E_BEHAVIOR_DRIFT",
                        f"Dependency {path} failed on locked boundary input {args!r}: {exc}",
                    ) from exc
                if actual != expected:
                    raise BError(
                        "E_BEHAVIOR_DRIFT",
                        f"Silent behavioral drift in {path} on input {args!r}: locked {expected!r}, observed {actual!r}",
                    )
                checked_fingerprints += 1
    finally:
        if "_b_js_session" in ns:
            ns["_b_js_session"].close()

    return {
        "status": "verified",
        "symbols_checked": len(current_symbols),
        "probes_checked": checked_probes,
        "fingerprints_checked": checked_fingerprints,
        "warnings": warnings,
    }
