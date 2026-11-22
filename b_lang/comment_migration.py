"""Copy legacy B source without its free-form comments."""
from io import StringIO
from pathlib import Path
import sys

from .types import BError


def _without_comment(line: str) -> str:
    if "#" not in line:
        return line
    quoted = escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
        elif quoted and char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == "#" and not quoted:
            ending = line[len(line.rstrip("\r\n")):]
            return line[:index] + ending
    return line


def strip_comments(source: str) -> str:
    return "".join(_without_comment(line) for line in StringIO(source, newline=""))


def add_command(sub):
    parser = sub.add_parser("migrate-comments", help="Print legacy B source with its # comments removed")
    parser.add_argument("file", type=Path)


def run(args, read_source):
    try:
        sys.stdout.write(strip_comments(read_source(args.file, newline="")))
    except (BError, OSError, ValueError) as exc:
        print(f"B migrate-comments: {exc}", file=sys.stderr)
        return 1
    return 0
