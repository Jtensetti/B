"""Command line interface for B (.bee preferred; .b4 experimental alias)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compiler import compile_b
from .types import BError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="b", description="B programming language v0.4")
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("check", "run", "build"):
        p = sub.add_parser(cmd)
        p.add_argument("file", type=Path, help="B source file (.bee preferred; .b4, .bsrc and .b supported)")
        p.add_argument("--strict", action="store_true", help="Reject unresolved static checks")
        if cmd == "check":
            p.add_argument("--json", action="store_true", help="Machine-readable diagnostics and foreign assumptions")
    inspect = sub.add_parser('inspect', help='Inspect Python static signatures or the .NET host metadata')
    inspect.add_argument('target', help='py:module.name or net:Full.Type.Name')
    inspect.add_argument('--json', action='store_true', help='Machine-readable result')
    inspect.add_argument('--live', action='store_true', help='Read live .NET metadata instead of the checked-in snapshot')
    inspect.add_argument('--verify', action='store_true', help='Fail if the live .NET metadata differs from the snapshot')
    args = parser.parse_args(argv)
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
        if args.file.suffix.lower() not in (".bee", ".b4", ".bsrc", ".b"):
            raise BError("E_EXTENSION", "Expected .bee (preferred), .b4, .bsrc or legacy .b source file")
        source = args.file.read_text(encoding="utf-8")
        result = compile_b(source, strict=False)
        if args.strict and result.diagnostics:
            if machine:
                print(json.dumps({
                    "status": "rejected", "language": "B", "spec": "0.4", "strict": True,
                    "error": {"code": "E_STRICT", "message": "Unresolved static warnings"},
                    "diagnostics": [vars(d) for d in result.diagnostics],
                    "assumed_foreign_contracts": result.assumptions,
                }, ensure_ascii=False))
                return 1
            raise BError("E_STRICT", "Unresolved checks: " + "; ".join(d.code for d in result.diagnostics))
        if args.command == "build":
            print(result.source, end="")
        elif args.command == "check":
            if machine:
                print(json.dumps({
                    "status": "accepted", "language": "B", "spec": "0.4",
                    "strict": args.strict,
                    "diagnostics": [vars(d) for d in result.diagnostics],
                    "assumed_foreign_contracts": result.assumptions,
                    "behavior_proven": False,
                }, ensure_ascii=False))
            else:
                for d in result.diagnostics:
                    print(f"{d.level.upper()} {d.code}: {d.message}")
                for assumption in result.assumptions:
                    print(f"ASSUMED FOREIGN CONTRACT: {assumption}")
                print(f"B check: {len(result.diagnostics)} unresolved warning(s); syntax and B types valid")
        elif args.command == "run":
            # Running B can run imported Python/.NET code; this is not a sandbox.
            namespace = {"__name__": "__b_program__"}
            exec(result.code, namespace, namespace)
        return 0
    except (BError, OSError, RuntimeError, AssertionError, ImportError, ValueError, TypeError, ZeroDivisionError) as exc:
        if machine:
            print(json.dumps({
                "status": "rejected", "language": "B", "spec": "0.4",
                "error": {"code": getattr(exc, "code", "E_RUNTIME"), "message": str(exc)},
            }, ensure_ascii=False))
        else:
            print(f"B {args.command}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
