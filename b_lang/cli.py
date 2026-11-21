"""Command line interface: b check/run/build <file.b>."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path
from .compiler import compile_b
from .types import BError

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="b", description="B programming language v0.1")
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("check", "run", "build"):
        p = sub.add_parser(cmd)
        p.add_argument("file", type=Path, help="B source file")
        p.add_argument("--strict", action="store_true", help="Reject unresolved static checks")
    args = parser.parse_args(argv)
    try:
        source = args.file.read_text(encoding="utf-8")
        result = compile_b(source, strict=args.strict)
        if args.command == "build":
            print(result.source, end="")
        elif args.command == "check":
            for d in result.diagnostics: print(f"{d.level.upper()} {d.code}: {d.message}")
            print(f"B check: {len(result.diagnostics)} unresolved warning(s); syntax and B types valid")
        elif args.command == "run":
            # Running a B program can run imported Python/.NET library code; not sandboxed.
            namespace = {"__name__": "__b_program__"}
            exec(result.code, namespace, namespace)
        return 0
    except (BError, OSError, RuntimeError, AssertionError, ImportError, ValueError, TypeError, ZeroDivisionError) as exc:
        print(f"B {args.command}: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
