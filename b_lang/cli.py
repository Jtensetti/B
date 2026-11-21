"""Command line interface for B (.bsrc preferred; .b legacy compatible)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compiler import compile_b
from .types import BError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="b", description="B programming language v0.2")
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("check", "run", "build"):
        p = sub.add_parser(cmd)
        p.add_argument("file", type=Path, help="B source file (.bsrc preferred; .b supported)")
        p.add_argument("--strict", action="store_true", help="Reject unresolved static checks")
        if cmd == "check":
            p.add_argument("--json", action="store_true", help="Machine-readable diagnostics and foreign assumptions")
    args = parser.parse_args(argv)
    machine = args.command == "check" and args.json
    try:
        if args.file.suffix.lower() not in (".bsrc", ".b"):
            raise BError("E_EXTENSION", "Expected .bsrc (preferred) or legacy .b source file")
        source = args.file.read_text(encoding="utf-8")
        result = compile_b(source, strict=False)
        if args.strict and result.diagnostics:
            if machine:
                print(json.dumps({
                    "status": "rejected", "language": "B", "spec": "0.2", "strict": True,
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
                    "status": "accepted", "language": "B", "spec": "0.2",
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
                "status": "rejected", "language": "B", "spec": "0.2",
                "error": {"code": getattr(exc, "code", "E_RUNTIME"), "message": str(exc)},
            }, ensure_ascii=False))
        else:
            print(f"B {args.command}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
