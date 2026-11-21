"""Command line interface for B (.bee preferred; .b4 experimental alias)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .compiler import compile_b
from .impact import compare
from .types import BError


SPEC_VERSION = __version__.rsplit(".", 1)[0]


def compile_file(path: Path):
    if path.suffix.lower() not in (".bee", ".b4", ".bsrc", ".b"):
        raise BError("E_EXTENSION", "Expected .bee (preferred), .b4, .bsrc or legacy .b source file")
    return compile_b(path.read_text(encoding="utf-8"))


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
        if cmd == "check":
            p.add_argument("--require-proofs", action="store_true", help="Reject any reported contract or divisor obligation without a static proof")
            p.add_argument("--json", action="store_true", help="Machine-readable diagnostics and foreign assumptions")
    ir_command = sub.add_parser("ir", help="Emit the checked, backend-neutral BIR as JSON")
    ir_command.add_argument("file", type=Path)
    ir_command.add_argument("--strict", action="store_true")
    ir_command.add_argument("--optimized", action="store_true", help="Show BIR after the safe optimization pass")
    audit_command = sub.add_parser("audit", help="Measure direct Python signatures visible to B; does not import target")
    audit_command.add_argument("target", help="py:module.name")
    audit_command.add_argument("--json", action="store_true")
    inspect = sub.add_parser('inspect', help='Inspect Python static signatures or the .NET host metadata')
    inspect.add_argument('target', help='py:module.name or net:Full.Type.Name')
    inspect.add_argument('--json', action='store_true', help='Machine-readable result')
    inspect.add_argument('--live', action='store_true', help='Read live .NET metadata instead of the checked-in snapshot')
    inspect.add_argument('--verify', action='store_true', help='Fail if the live .NET metadata differs from the snapshot')
    adopt_audit = sub.add_parser("adopt-audit", help="List Python leaf functions B can compile as checked native functions")
    adopt_audit.add_argument("target", help="py:module.name")
    adopt_audit.add_argument("--json", action="store_true")
    impact = sub.add_parser("impact", help="Compare contract obligations in two revisions")
    impact.add_argument("before", type=Path)
    impact.add_argument("after", type=Path)
    impact.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
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
            else:
                raise BError('E_IMPORT', 'Expected py: or net: prefix')
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
        result = compile_file(args.file)
        unresolved = [o for o in result.analysis.obligations if o.status != "proved"]
        rejection = None
        if args.strict and result.diagnostics:
            rejection = BError("E_STRICT", "Unresolved checks: " + "; ".join(d.code for d in result.diagnostics))
        elif args.command == "check" and args.require_proofs and unresolved:
            rejection = BError("E_PROOF_REQUIRED", f"{len(unresolved)} obligation(s) lack a static proof")
        if rejection and not machine:
            if args.command == "check":
                for item in unresolved:
                    print(item.describe(), file=sys.stderr)
            raise rejection
        if args.command == "ir":
            print(json.dumps((result.optimized_ir if args.optimized else result.ir).to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
        elif args.command == "build":
            print(result.source, end="")
        elif args.command == "check":
            if machine:
                print(json.dumps({
                    "status": "rejected" if rejection else "accepted", "language": "B", "spec": SPEC_VERSION,
                    **({"error": {"code": rejection.code, "message": rejection.message}} if rejection else {}),
                    "contract_analysis": result.analysis.to_dict(),
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
                for assumption in result.assumptions:
                    print(f"ASSUMED FOREIGN CONTRACT: {assumption}")
                print(f"B check: {len(result.diagnostics)} warning(s), {len(unresolved)} unproved obligation(s)")
            return 1 if rejection else 0
        elif args.command == "run":
            # Running B can run imported Python/.NET code; this is not a sandbox.
            namespace = {"__name__": "__b_program__"}
            exec(result.code, namespace, namespace)
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
