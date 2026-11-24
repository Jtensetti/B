"""Command line interface for B (.bee preferred; .b4 experimental alias)."""
from __future__ import annotations

import argparse
import os
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
            p.add_argument("--json", action="store_true", help="Machine-readable diagnostics and foreign assumptions")
            p.add_argument("--library-examples", action="store_true",
                           help="Run each example of an imported function on its own and report it")
    ir_command = sub.add_parser("ir", help="Emit the checked, backend-neutral BIR as JSON")
    ir_command.add_argument("file", type=Path)
    ir_command.add_argument("--strict", action="store_true")
    ir_command.add_argument("--optimized", action="store_true", help="Show BIR after the safe optimization pass")
    audit_command = sub.add_parser("audit", help="Measure direct Python signatures visible to B; does not import target")
    audit_command.add_argument("target", help="py:module.name")
    audit_command.add_argument("--json", action="store_true")
    inspect = sub.add_parser('inspect', help='Inspect Python, Node.js or .NET function signatures')
    inspect.add_argument('target', help='py:module.name, js:package or net:Full.Type.Name')
    inspect.add_argument('--json', action='store_true', help='Machine-readable result')
    inspect.add_argument('--live', action='store_true', help='Read live .NET metadata instead of the checked-in snapshot')
    inspect.add_argument('--verify', action='store_true', help='Fail if the live .NET metadata differs from the snapshot')
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
    ask_command = sub.add_parser("ask", help="Find the input an also declaration leaves ambiguous and ask one question")
    ask_command.add_argument("file", type=Path)
    ask_command.add_argument("--with", dest="delta", type=Path, metavar="DELTA.bee",
                             help="Examine the also declarations in a separate file")
    ask_command.add_argument("--answer", metavar="VALUE", help="Answer the open question with one of the offered values")
    ask_command.add_argument("--apply", action="store_true", help="Write the answered revision back to the files")
    ask_command.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    program = getattr(args, "file", None)
    if isinstance(program, Path):
        # As Python does for a script: modules next to the program can be imported.
        folder = str(program.resolve().parent)
        if folder not in sys.path:
            sys.path.insert(0, folder)
        os.environ["B_PROGRAM_DIR"] = folder  # local go: and rust: packages are found from here
    if args.command == "ask":
        from . import ask_cli
        return ask_cli.run(args, read_source)
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
            else:
                raise BError('E_IMPORT', 'Expected py:, js: or net: prefix')
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
            print(result.source, end="")
        elif args.command == "check" and args.library_examples and not rejection:
            from .library_examples import run_each
            results = run_each(result.ir)
            if machine:
                print(json.dumps({"status": "accepted", "library_examples": results}, ensure_ascii=False))
            else:
                for row in results:
                    print(f"{row['status']}: {row['example']}" + (f"\n    {row['message']}" if "message" in row else ""))
                print(f"B check: {sum(r['status'] == 'holds' for r in results)} of {len(results)} library example(s) hold")
            return int(any(r["status"] != "holds" for r in results))
        elif args.command == "check":
            if machine:
                print(json.dumps({
                    "status": "rejected" if rejection else "accepted", "language": "B", "spec": SPEC_VERSION,
                    **({"error": {"code": rejection.code, "message": rejection.message}} if rejection else {}),
                    "contract_analysis": result.analysis.to_dict(),
                    **({"pending_analysis": result.pending_analysis.to_dict()} if result.pending_analysis is not None else {}),
                    "conditional_guarantees": use_rules,
                    **({"joint_checks": joint_checks} if joint_checks else {}),
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
            # Imports can execute real library code in their respective runtimes.
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
