"""List typed handoff instructions or apply their checked revision to the source."""
import os
from pathlib import Path
import stat
import sys
import tempfile

from .types import BError


def add_command(sub):
    parser = sub.add_parser("next", help="List or apply the source file's pending instructions")
    parser.add_argument("file", type=Path)
    parser.add_argument("--from-short", type=Path, metavar="ROWS",
                        help="Read compact edit rows from a UTF-8 file or - for standard input")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--context", action="store_true", help="Show each current target declaration with its instruction")
    action.add_argument("--apply", action="store_true", help="Write the checked changes and consume the instructions")
    parser.add_argument("--strict", action="store_true", help="Reject unresolved static warnings in either revision")


def _replace_checked(path, target, source, revision):
    # Replace in the original directory so readers see either complete revision.
    staged = tempfile.NamedTemporaryFile(dir=target.parent, prefix=".b-next-", delete=False)
    temp_path = Path(staged.name)
    try:
        with staged:
            staged.write(revision.encode("utf-8"))
            staged.flush()
            os.fsync(staged.fileno())
        with target.open("rb+") as current:
            if os.name == "posix":
                import fcntl
                fcntl.flock(current, fcntl.LOCK_EX)
            original_stat = os.fstat(current.fileno())
            if (current.read() != source.encode("utf-8") or path.resolve(strict=True) != target
                    or not os.path.samestat(target.stat(), original_stat)):
                raise BError("E_HANDOFF_CHANGED", "The source changed while checking the handoff. Read the current instructions again.")
            temp_path.chmod(stat.S_IMODE(original_stat.st_mode))
            if os.name == "nt":
                # Windows requires closing the original before a rename over it.
                current.close()
            os.replace(temp_path, target)
    finally:
        temp_path.unlink(missing_ok=True)


def run(args, read_source):
    from .handoff import inspect_handoff
    try:
        target = args.file.resolve(strict=True)
        source = read_source(args.file, newline="")
        if args.from_short is None:
            instructions, revision = inspect_handoff(source, strict=args.strict, include_context=args.context)
        else:
            from .shorthand import prepare_shorthand
            rows = sys.stdin.read() if args.from_short == Path("-") else args.from_short.read_text(encoding="utf-8")
            expanded, handoff = prepare_shorthand(source, rows, strict=args.strict)
            if handoff is None:
                return 0
            instructions = handoff.entries(expanded, include_context=args.context)
            revision = handoff.source
            if not source.endswith(("\r", "\n")):
                # The separator before the temporary instructions is outside the original file.
                revision = revision.rstrip("\r\n")
        if args.apply:
            if instructions:
                _replace_checked(args.file, target, source, revision)
        else:
            for directive in instructions:
                print(directive)
    except (BError, OSError, ValueError, RuntimeError) as exc:
        print(f"B next: {exc}", file=sys.stderr)
        return 1
    return 0
