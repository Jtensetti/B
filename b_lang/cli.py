"""Command line interface for B (.bee preferred; .b4 experimental alias)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, clarify_cli, comment_migration, handoff_cli, register_view
from .compiler import compile_b
from .impact import compare
from .types import BError


SPEC_VERSION = __version__.rsplit(".", 1)[0]


def read_source(path: Path, *, newline: str | None = None) -> str:
    if path.suffix.lower() not in (".bee", ".b4", ".bsrc", ".b"):
        raise BError("E_EXTENSION", "Expected .bee (preferred), .b4, .bsrc or legacy .b source file")
    with path.open(encoding="utf-8", newline=newline) as stream:
        return stream.read()


def compile_file(path: Path, *, conditional_guarantees: bool = True, delta_path: Path | None = None):
    source = read_source(path)
    if delta_path is not None:
        from .revisions import attach_delta
        source = attach_delta(source, read_source(delta_path))
    return compile_b(source, conditional_guarantees=conditional_guarantees)


def show_revision(args) -> int:
    from .revisions import check_revision
    try:
        delta = read_source(args.delta) if args.delta else None
        report = check_revision(read_source(args.before), read_source(args.after), delta=delta)
    except (BError, OSError, UnicodeError) as exc:
        report = {"status": "invalid", "reason": str(exc)}
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(f"{report['status']}: {report.get('reason') or report.get('method', '')}")
        if report['status'] == 'counterexample' and 'function' in report:
            args_text = json.dumps(report.get('arguments'), ensure_ascii=False)
            print(f"{report['function']} {args_text}: expected {report.get('expected')!r}, "
                  f"got {report.get('actual')!r}")
        elif 'output_index' in report:
            print(f"print {report['output_index']}: expected {report['expected']!r}, "
                  f"got {report['actual']!r}")
    return int(report["status"] != "proved")


def show_impact(args) -> int:
    revisions = []
    for revision, path in (("before", args.before), ("after", args.after)):
        try:
            revisions.append(compile_file(path).analysis)
        except (BError, OSError, ValueError, RuntimeError) as exc:
            error = {"code": getattr(exc, "code", "E_INPUT"), "message": str(exc)}
            if args.json:
                print(json.dumps({"status": "rejected", "revision": revision, "error": error}))
            else:
                print(f"B impact ({revision}, {path}): {exc}", file=sys.stderr)
            return 1
    report = compare(*revisions)
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        for row in report["changes"]:
            old, new = row["before"], row["after"]
            item = new or old
            location = f"{old['site']} -> {new['site']}" if row["moved"] else item["site"]
            condition = item["requirement"]
            if old and new and old["requirement"] != new["requirement"]:
                condition = f"{old['requirement']} -> {new['requirement']}"
            print(f"{row['change']} {item['caller']} [{location}] {condition}: "
                  f"{old['status'] if old else '-'} -> {new['status'] if new else '-'}")
        print(f"{len(report['changes'])} changed obligation(s), {report['unchanged']} unchanged")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="b", description=f"B programming language v{SPEC_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("check", "run", "build"):
        p = sub.add_parser(cmd)
        p.add_argument("file", type=Path, help="B source file (.bee preferred; .b4, .bsrc and .b supported)")
        p.add_argument("--strict", action="store_true", help="Reject unresolved static checks")
        p.add_argument("--with", dest="delta", type=Path, metavar="DELTA.bee",
                       help="Compile with a file of executable also declarations")
        if cmd == "check":
            p.add_argument("--joint", action="append", default=[], type=Path, metavar="REQUEST",
                           help="Check a relation on pairs of native calls in an explicit grid (repeatable)")
            p.add_argument("--no-conditional-guarantees", action="store_true",
                           help="Run the same checker with conditional result guarantees disabled")
            p.add_argument("--explain", action="store_true",
                           help="Explain open divisor and integer argument checks")
            p.add_argument("--require-proofs", action="store_true", help="Reject any reported contract or divisor obligation without a static proof")
            p.add_argument("--lock", type=Path, metavar="LOCK.json",
                           help="Verify signatures, semantic facets and behavioral probes against a dependency lockfile before execution")
            p.add_argument("--json", action="store_true", help="Machine-readable diagnostics and foreign assumptions")
        elif cmd == "build":
            p.add_argument("--target", choices=("py", "js"), default="py",
                           help="Target lowering backend (py or js)")
        elif cmd == "run":
            p.add_argument("--backend", choices=("py", "js"), default="py",
                           help="Execution backend (py or js)")
    lock_cmd = sub.add_parser("lock", help="Create or verify a behavioral dependency lockfile")
    lock_cmd.add_argument("file", type=Path, help="B source file")
    lock_cmd.add_argument("--out", type=Path, metavar="LOCK.json", help="Lockfile path (default: FILE.lock.json)")
    lock_cmd.add_argument("--verify", action="store_true", help="Verify against an existing lockfile instead of writing one")
    lock_cmd.add_argument("--strict", action="store_true", help="Reject unresolved static warnings")
    lock_cmd.add_argument("--json", action="store_true", help="Machine-readable report")
    ir_command = sub.add_parser("ir", help="Emit the checked, backend-neutral BIR as JSON")
    ir_command.add_argument("file", type=Path)
    ir_command.add_argument("--strict", action="store_true")
    ir_command.add_argument("--optimized", action="store_true", help="Show BIR after the safe optimization pass")
    audit_command = sub.add_parser("audit", help="Measure direct Python signatures visible to B; does not import target")
    audit_command.add_argument("target", help="py:module.name")
    audit_command.add_argument("--json", action="store_true")
    inspect = sub.add_parser('inspect', help='Inspect Python, Node.js, .NET, Go or Rust function signatures')
    inspect.add_argument('target', help='py:module.name, js:package, net:Full.Type.Name, go:pkg or rs:mod')
    inspect.add_argument('--json', action='store_true', help='Machine-readable result')
    inspect.add_argument('--live', action='store_true', help='Read live host metadata instead of the checked-in snapshot')
    inspect.add_argument('--verify', action='store_true', help='Fail if the live host metadata differs from the snapshot')
    adopt_audit = sub.add_parser("adopt-audit", help="List Python leaf functions B can compile as checked native functions")
    adopt_audit.add_argument("target", help="py:module.name")
    adopt_audit.add_argument("--json", action="store_true")
    discover = sub.add_parser("discover", help="Propose and check an integer result contract from the current implementation")
    discover.add_argument("file", type=Path)
    discover.add_argument("--function", required=True, help="Name of the native B function")
    discover.add_argument("--expect", help="Require proof of an independent affine equality, e.g. 'result == free + booked'")
    discover.add_argument("--trace", action="store_true", help="Include the observations and eliminated candidates")
    discover.add_argument("--json", action="store_true", help="Emit a machine-readable report")
    register_view.add_command(sub)
    handoff_cli.add_command(sub)
    comment_migration.add_command(sub)
    clarify_cli.add_command(sub)
    impact = sub.add_parser("impact", help="Compare contract obligations in two revisions")
    impact.add_argument("before", type=Path)
    impact.add_argument("after", type=Path)
    impact.add_argument("--json", action="store_true")
    revision = sub.add_parser("revision", help="Check a candidate against the accepted program plus its declared change")
    revision.add_argument("before", type=Path)
    revision.add_argument("after", type=Path)
    revision.add_argument("--delta", type=Path, help="Pin the authorized change from a separate .bee file")
    revision.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "lock":
        from .lock import create_lock, verify_lock
        lock_path = args.out or args.file.with_suffix(args.file.suffix + ".lock.json")
        try:
            source = read_source(args.file)
            if args.verify:
                lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
                report = verify_lock(source, lock_data, source_file=args.file, strict=args.strict)
            else:
                lock_data = create_lock(source, source_file=args.file)
                lock_path.write_text(json.dumps(lock_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                report = {
                    "status": "locked",
                    "lockfile": str(lock_path),
                    "symbols": len(lock_data["symbols"]),
                    "probes": len(lock_data["probes"]),
                    "fingerprints": sum(len(v) for v in lock_data["fingerprints"].values()),
                }
            if args.json:
                print(json.dumps(report, ensure_ascii=False))
            else:
                print(f"B lock: {report['status']} ({lock_path})")
            return 0
        except (BError, OSError, ValueError, RuntimeError) as exc:
            if args.json:
                print(json.dumps({"status": "rejected", "error": {"code": getattr(exc, "code", "E_LOCK"), "message": str(exc)}}, ensure_ascii=False))
            else:
                print(f"B lock: {exc}", file=sys.stderr)
            return 1
    if args.command == "revision":
        return show_revision(args)
    if args.command == "next":
        return handoff_cli.run(args, read_source)
    if args.command == "migrate-comments":
        return comment_migration.run(args, read_source)
    if args.command == "view":
        return register_view.run(args, read_source)
    if args.command == "clarify":
        return clarify_cli.run(args, compile_file)
    if args.command == "discover":
        from .proposals import report
        try:
            data = report(compile_file(args.file).ir, args.function, expect=args.expect, trace=args.trace)
        except (BError, OSError, ValueError, RuntimeError) as exc:
            if args.json:
                print(json.dumps({"status": "rejected", "error": {"code": getattr(exc, "code", "E_INPUT"), "message": str(exc)}}))
            else:
                print(f"B discover: {exc}", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(data, ensure_ascii=False))
        else:
            print(f"{data['function']}: {data['status']}. {data['reason']}")
            if data['proposed_contract']:
                print(f"{data['proposed_contract']} ({data['verification']['status']} for the current implementation)")
            if data["declared_counterexample"]:
                print("Declared postcondition counterexample:", json.dumps(data["declared_counterexample"]))
            elif data["declared_audit"] in {"unsupported", "incomplete", "unobserved"}:
                print("Declared postcondition audit:", data["declared_audit"])
            if "expectation" in data:
                print("Supplied expectation:", json.dumps(data["expectation"]))
            if args.trace:
                print(json.dumps(data["trace"], indent=2))
        return int(args.expect is not None and data["expectation"]["status"] != "proved")
    if args.command == "impact":
        return show_impact(args)
    if args.command == "adopt-audit":
        from .adoption import audit_adoptable
        try:
            if not args.target.startswith("py:"):
                raise BError("E_ADOPT", "Expected py:module.name")
            report = audit_adoptable(args.target[3:])
            if args.json:
                print(json.dumps(report, ensure_ascii=False, sort_keys=True))
            else:
                print(f"{report['target']}: {report['adoptable']}/{report['public_top_level_functions']} adoptable source functions")
                for name in report['accepted']:
                    print(f"  + {name}")
                for name, data in report['rejected'].items():
                    print(f"  - {name}: {data['code']} {data['reason']}")
            return 0
        except (BError, OSError, RuntimeError) as exc:
            if args.json:
                print(json.dumps({"status": "rejected", "error": {"code": getattr(exc, "code", "E_ADOPT"), "message": str(exc)}}, ensure_ascii=False))
            else:
                print(f"B adopt-audit: {exc}", file=sys.stderr)
            return 1

    if args.command == "audit":
        from .audit import audit_python
        try:
            if not args.target.startswith("py:"):
                raise BError("E_IMPORT", "audit currently accepts py:module only")
            data = audit_python(args.target[3:]).to_dict()
            if args.json:
                print(json.dumps(data, ensure_ascii=False, sort_keys=True))
            else:
                print(f"{data['target']}: {data['static_signatures']}/{data['public_direct_functions']} direct public functions supported")
                print(f"  named re-exports: {data['named_reexports']}; star re-exports: {data['star_reexports']}; classes: {data['public_classes']}")
                print("  Note: this is NOT total package/API coverage; runtime behavior is not verified")
            return 0
        except (BError, OSError, RuntimeError) as exc:
            if args.json:
                print(json.dumps({"status": "rejected", "error": {"code": getattr(exc, "code", "E_METADATA"), "message": str(exc)}}))
            else:
                print(f"B audit: {exc}", file=sys.stderr)
            return 1
    if args.command == 'inspect':
        from .discovery import inspect_python
        from .netmeta import manifest, describe_live
        try:
            if args.target.startswith('py:'):
                if args.live or args.verify:
                    raise BError('E_USAGE', '--live and --verify require a net: target')
                name = args.target[3:]
                found = inspect_python(name)
                from .types import Overloads
                signatures = []
                for name, binding in sorted(found.signatures.items()):
                    options = binding.options if isinstance(binding, Overloads) else (binding,)
                    for idx, sig in enumerate(options, start=1):
                        signatures.append(dict(name=name, parameters=[str(t) for t in sig.params],
                                               result=str(sig.result), min_arity=sig.required,
                                               overload=len(options) > 1, variant=idx))
                result = {
                    'target': args.target, 'origin': found.source, 'provenance': found.source_kind,
                    'signatures': signatures, 'skipped': found.skipped,
                    'behavior_proven': False,
                }
                if found.source_kind == 'unavailable':
                    raise BError('E_IMPORT', f'Python module {name} is not installed')
            elif args.target.startswith('js:'):
                from .jsmeta import describe
                if args.live or args.verify:
                    raise BError('E_USAGE', '--live and --verify require a net: target')
                result = describe(args.target[3:])
            elif args.target.startswith('net:'):
                current = describe_live() if (args.live or args.verify) else manifest()
                if args.verify and current != manifest():
                    raise BError('E_METADATA', 'Live .NET signatures differ from checked-in manifest')
                name = args.target[4:]
                if name not in current['types']:
                    raise BError('E_IMPORT', f'No .NET host signatures for {name}')
                result = {'target': args.target, 'origin': current['runtime'],
                          'provenance': 'live-reflection' if args.live or args.verify else 'verified-snapshot',
                          'signatures': [dict(name=m['name'], parameters=m['params'],
                                              result=m['result'], min_arity=len(m['params']))
                                         for m in current['types'][name]],
                          'behavior_proven': False}
            elif args.target.startswith('go:'):
                from . import gometa
                current = gometa.describe_live() if (args.live or args.verify) else gometa.manifest()
                if args.verify and current != gometa.manifest():
                    raise BError('E_METADATA', 'Live Go signatures differ from checked-in manifest')
                name = args.target[3:]
                if name not in current['packages']:
                    raise BError('E_IMPORT', f'No Go host signatures for {name}')
                result = {'target': args.target, 'origin': current['runtime'],
                          'provenance': 'live-go-host' if args.live or args.verify else 'verified-go-snapshot',
                          'signatures': [dict(name=m['name'], parameters=m['params'],
                                              result=m['result'], min_arity=len(m['params']))
                                         for m in current['packages'][name]],
                          'behavior_proven': False}
            elif args.target.startswith('rs:'):
                from . import rsmeta
                current = rsmeta.describe_live() if (args.live or args.verify) else rsmeta.manifest()
                if args.verify and current != rsmeta.manifest():
                    raise BError('E_METADATA', 'Live Rust signatures differ from checked-in manifest')
                name = args.target[3:]
                if name not in current['modules']:
                    raise BError('E_IMPORT', f'No Rust host signatures for {name}')
                result = {'target': args.target, 'origin': current['runtime'],
                          'provenance': 'live-rs-host' if args.live or args.verify else 'verified-rs-snapshot',
                          'signatures': [dict(name=m['name'], parameters=m['params'],
                                              result=m['result'], min_arity=len(m['params']))
                                         for m in current['modules'][name]],
                          'behavior_proven': False}
            else:
                raise BError('E_IMPORT', 'Expected py:, js:, net:, go: or rs: prefix')
            if args.json:
                print(json.dumps(result, ensure_ascii=False))
            else:
                print(f"{result['target']} ({result['provenance']})")
                for row in result['signatures']:
                    print(f"  {row['name']}({', '.join(row['parameters'])}) -> {row['result']}")
            return 0
        except (BError, OSError, RuntimeError) as exc:
            if args.json:
                print(json.dumps({'status':'rejected', 'error':{'code':getattr(exc, 'code','E_METADATA'),
                                                              'message':str(exc)}}))
            else:
                print(f'B inspect: {exc}', file=sys.stderr)
            return 1
    machine = args.command == "check" and args.json
    try:
        use_rules = args.command != "check" or not args.no_conditional_guarantees
        result = compile_file(args.file, conditional_guarantees=use_rules,
                              delta_path=getattr(args, "delta", None))
        hints = []
        if args.command == "check" and args.explain:
            from .guidance import guidance
            hints = guidance(result.ir, result.analysis, conditional_guarantees=use_rules)
        unresolved = [o for o in result.analysis.obligations if o.status != "proved"]
        pending_unresolved = ([o for o in result.pending_analysis.obligations if o.status != "proved"]
                              if result.pending_analysis is not None else [])
        rejection = None
        if args.strict and result.diagnostics:
            rejection = BError("E_STRICT", "Unresolved checks: " + "; ".join(d.code for d in result.diagnostics))
        elif args.command == "check" and args.require_proofs and unresolved:
            rejection = BError("E_PROOF_REQUIRED", f"{len(unresolved)} obligation(s) lack a static proof")
        elif args.command == "check" and args.require_proofs and pending_unresolved:
            rejection = BError("E_PROOF_REQUIRED", f"{len(pending_unresolved)} obligation(s) in the pending revision lack a static proof")
        lock_report = None
        if args.command == "check" and getattr(args, "lock", None) is not None and rejection is None:
            from .lock import verify_lock
            lock_data = json.loads(args.lock.read_text(encoding="utf-8"))
            lock_report = verify_lock(read_source(args.file), lock_data, source_file=args.file, strict=args.strict)
        joint_checks = []
        if args.command == "check" and args.joint:
            from .joint_cli import describe, run_checks
            joint_checks = run_checks(result.ir, args.joint)
            failed = [row for row in joint_checks if row["status"] != "passed"]
            if failed and rejection is None:
                first = failed[0]
                code = first.get("code", "E_JOINT_" + first["status"].upper())
                rejection = BError(code, f"{len(failed)} of {len(joint_checks)} joint requirements did not pass")
            if not machine:
                for row in joint_checks:
                    print(describe(row), file=sys.stdout if row["status"] == "passed" else sys.stderr)
        if rejection and not machine:
            if args.command == "check":
                for item in unresolved:
                    print(item.describe(), file=sys.stderr)
                for item in pending_unresolved:
                    print(f"Pending handoff: {item.describe()}", file=sys.stderr)
                for hint in hints:
                    print(f"{hint['caller']} [{hint['site']}] {hint['detail']} {hint['suggestion']}", file=sys.stderr)
            raise rejection
        if args.command == "ir":
            print(json.dumps((result.optimized_ir if args.optimized else result.ir).to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "build":
            if args.target == "js":
                from .lowering_js import JavaScriptLowerer
                print(JavaScriptLowerer().lower(result.optimized_ir), end="")
            else:
                print(result.source, end="")
        elif args.command == "check":
            if machine:
                print(json.dumps({
                    "status": "rejected" if rejection else "accepted", "language": "B", "spec": SPEC_VERSION,
                    **({"error": {"code": rejection.code, "message": rejection.message}} if rejection else {}),
                    "contract_analysis": result.analysis.to_dict(),
                    **({"pending_analysis": result.pending_analysis.to_dict()} if result.pending_analysis is not None else {}),
                    "conditional_guarantees": use_rules,
                    **({"joint_checks": joint_checks} if joint_checks else {}),
                    **({"lock_verification": lock_report} if lock_report is not None else {}),
                    **({"guidance": hints} if args.explain else {}),
                    "strict": args.strict,
                    "diagnostics": [vars(d) for d in result.diagnostics],
                    "assumed_foreign_contracts": result.assumptions,
                    "behavior_proven": False,
                    "detected_effects": list(result.ir.detected_effects),
                    "permitted_effects": list(result.ir.permitted_effects) if result.ir.permitted_effects is not None else None,
                    "function_contracts": [{"name": s.name, "declared_pure": s.declared_pure,
                       "effects": list(s.effects), "postcondition_status": s.verification,
                       "precondition_runtime_checked": s.requires is not None} for s in result.ir.statements if s.op == "fn"],
                }, ensure_ascii=False))
            else:
                for d in result.diagnostics:
                    print(f"{d.level.upper()} {d.code}: {d.message}")
                for item in unresolved:
                    if item.kind == "nonzero":
                        print(item.describe())
                for hint in hints:
                    print(f"{hint['caller']} [{hint['site']}] {hint['detail']} {hint['suggestion']}")
                for assumption in result.assumptions:
                    print(f"ASSUMED FOREIGN CONTRACT: {assumption}")
                print(f"B check: {len(result.diagnostics)} warning(s), {len(unresolved)} unproved obligation(s)")
                if result.pending_analysis is not None:
                    print(f"Pending handoff: {len(pending_unresolved)} unproved obligation(s)")
            return 1 if rejection else 0
        elif args.command == "run":
            if args.backend == "js":
                import shutil, subprocess, tempfile
                from .lowering_js import JavaScriptLowerer
                node = shutil.which("node")
                if not node:
                    raise BError("E_BACKEND", "Node.js is required for --backend js")
                js_code = JavaScriptLowerer().lower(result.optimized_ir)
                with tempfile.NamedTemporaryFile("w", suffix=".cjs", dir=str(args.file.resolve().parent), delete=True, encoding="utf-8") as tmp:
                    tmp.write(js_code)
                    tmp.flush()
                    proc = subprocess.run([node, tmp.name], check=False)
                    return proc.returncode
            namespace = {"__name__": "__b_program__"}
            if any(s.op == "import" and s.backend == "js" for s in result.ir.statements):
                namespace["__file__"] = str(args.file.resolve())
            try:
                exec(result.code, namespace, namespace)
            finally:
                if "_b_js_session" in namespace:
                    namespace["_b_js_session"].close()
        return 0
    except (BError, OSError, RuntimeError, AssertionError, ImportError, ValueError, TypeError, ZeroDivisionError) as exc:
        if machine:
            print(json.dumps({
                "status": "rejected", "language": "B", "spec": SPEC_VERSION,
                "error": {"code": getattr(exc, "code", "E_RUNTIME"), "message": str(exc)},
            }, ensure_ascii=False))
        else:
            print(f"B {args.command}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
