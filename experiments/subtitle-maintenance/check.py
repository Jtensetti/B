"""Lecture subtitle timing QC for the project's supported WebVTT profile."""
import argparse
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from html import unescape
from pathlib import Path
import re
import sys

POLICIES = Path(__file__).resolve().parent
Policy = Callable[[int, int, int, int, int, bool], str]
STAMP = r"(?:(\d{2,}):)?([0-5]\d):([0-5]\d)\.(\d{3})"
ARROW = re.compile(r"(\S+)[ \t]+-->[ \t]+(\S+)(?:[ \t]+[^\n]+)?")
MARKUP = re.compile(r"<[^<>]*>")
WORD = re.compile(r"[^\W_]+(?:[-'’][^\W_]+)*")


@dataclass(frozen=True)
class Cue:
    line: int
    name: str
    start: int
    end: int
    words: int
    effect: bool


def millis(value: str) -> int:
    match = re.fullmatch(STAMP, value, re.ASCII)
    if not match:
        raise ValueError(f"invalid timestamp {value!r}")
    hours, minutes, seconds, ms = match.groups()
    return ((int(hours or 0) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(ms)


def read_cues(text: str) -> Iterator[Cue]:
    lines = text.removeprefix("\ufeff").splitlines()
    if not lines or not re.fullmatch(r"WEBVTT(?:[ \t].*)?", lines[0]) or "-->" in lines[0]:
        raise ValueError("expected WEBVTT header")
    if len(lines) > 1 and lines[1].strip():
        raise ValueError("expected a blank line after the WEBVTT header")
    index, previous_start = 1, -1
    while index < len(lines):
        if not lines[index].strip():
            index += 1
            continue
        first = index
        while index < len(lines) and lines[index].strip():
            index += 1
        block = lines[first:index]
        if re.fullmatch(r"NOTE(?:[ \t].*)?", block[0]) or block[0] in ("STYLE", "REGION"):
            continue
        named = "-->" not in block[0]
        timing_index = int(named)
        match = ARROW.fullmatch(block[timing_index]) if timing_index < len(block) else None
        if not match:
            raise ValueError(f"line {first + timing_index + 1}: expected cue timing")
        start, end = (millis(stamp) for stamp in match.groups())
        if start < previous_start:
            raise ValueError(f"line {first + timing_index + 1}: cue starts are out of order")
        previous_start = start
        plain = unescape(MARKUP.sub("", " ".join(block[timing_index + 1:]))).strip()
        yield Cue(first + timing_index + 1, block[0] if named else "", start, end,
                  len(WORD.findall(plain)), re.fullmatch(r"\[[^\[\]]+\]", plain) is not None)


def load_policy(language: str, revision: int, path: Path | None = None) -> Policy:
    suffix = {"b": "bee", "python": "py"}[language]
    if revision == 0:
        from protocol import BASE
        source = BASE[suffix]
    else:
        source = (path or POLICIES / f"rev{revision}.{suffix}").read_text(encoding="utf-8")
    if suffix == "bee":
        from b_lang.compiler import compile_b
        code = compile_b(source, strict=True).code
    else:
        code = compile(source, f"<subtitle-policy-{revision}>", "exec")
    namespace = {}
    exec(code, namespace)
    return namespace["classify"]


def findings(cues: Iterator[Cue], classify: Policy) -> Iterator[tuple[Cue, str]]:
    spoken_until = effect_until = 0
    for cue in cues:
        issue = classify(cue.start, cue.end, spoken_until, effect_until, cue.words, cue.effect)
        if issue != "ok":
            yield cue, issue
        if cue.end > cue.start:
            if cue.effect:
                effect_until = max(effect_until, cue.end)
            else:
                spoken_until = max(spoken_until, cue.end)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--engine", choices=("b", "python"), default="b")
    parser.add_argument("--revision", type=int, choices=(0, 1, 2), default=2)
    args = parser.parse_args()
    try:
        issues = list(findings(read_cues(args.file.read_text(encoding="utf-8")), load_policy(args.engine, args.revision)))
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2
    for cue, issue in issues:
        print(f"{cue.line}\t{cue.name or '-'}\t{issue}")
    return int(bool(issues))


if __name__ == "__main__":
    raise SystemExit(main())
