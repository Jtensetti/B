"""Command line rendering for `b ask`."""
from __future__ import annotations

import json
import sys

from .ask import answer, ask, parse_answer
from .precedent import call_text, literal
from .types import BError


def _public(value):
    if isinstance(value, dict):
        return {k: _public(v) for k, v in value.items() if not k.startswith("_")}
    if isinstance(value, list):
        return [_public(v) for v in value]
    return value


def _render_examples(entry: dict) -> list[str]:
    lines = [f"{entry['declaration']} ({entry['examples']} examples)", f"  derived: {entry['rule']}"]
    if entry["status"] == "settled":
        lines.append(f"  settled: {entry['reason']}")
        return lines
    lines.append(f"  question: {entry['question']}")
    if entry.get("why"):
        lines.append(f"  why: {entry['why']}")
    if entry["status"] == "unseen":
        lines.append(f"  {entry['reason']}")
        return lines
    for option in entry["options"]:
        state = "settled" if option["settled"] else "still open"
        lines.append(f"    {literal(option['value'])}: {option['declaration']}")
        lines.append(f"        then: {option['rule']} ({state})")
    return lines


def _render(entry: dict) -> list[str]:
    if entry.get("kind") == "examples":
        return _render_examples(entry)
    lines = [entry["declaration"]]
    for change in entry.get("changes", []):
        lines.append(f"  {call_text(change['function'], tuple(change['arguments'].values()))}: "
                     f"{literal(change['before'])} -> {literal(change['after'])}")
    status = entry["status"]
    if status in ("checked", "no-change", "no-precedent"):
        lines.append(f"  {status}: {entry['reason']}")
        return lines
    precedent = entry["precedent"]
    target = entry["declaration"].split()[1].split("(")[0]
    lines.append(f"  nearest existing case: {call_text(target, tuple(precedent))}")
    for row in entry.get("uncompared", []):
        lines.append(f"  not compared: {row['function']} ({row['reason']})")
    if status == "settled":
        lines.append(f"  settled, no question: {entry['reason']}")
        lines.append(f"  record it: {entry['suggestion']}")
        return lines
    for row in entry["differences"]:
        lines.append(f"  {row['function']}: {literal(row['value'])} here, "
                     f"{literal(row['precedent_value'])} in the existing case")
    if status == "answered":
        lines.append(f"  answered: {entry['reason']}")
        return lines
    lines.append(f"  starts in: {', '.join(entry['causes'])}")
    lines.append(f"  question: {entry['question']}")
    for option in entry["options"]:
        lines.append(f"    {literal(option['value'])} ({option['meaning']}): {option['declaration']}")
        for repair in option["repairs"]:
            lines.append(f"        and in {repair['function']}: {repair['replace']} -> {repair['with']}")
        if not option["applicable"]:
            lines.append(f"        B cannot write this automatically; edit {', '.join(entry['causes'])} first")
    return lines


def run(args, read_source) -> int:
    try:
        delta = read_source(args.delta) if args.delta else None
        report = ask(read_source(args.file), delta)
        texts = None
        if args.answer is not None:
            texts = answer(report, parse_answer(args.answer))
            if args.apply:
                args.file.write_text(texts["file"], encoding="utf-8")
                if args.delta:
                    args.delta.write_text(texts["delta"], encoding="utf-8")
    except (BError, OSError, UnicodeError) as exc:
        if args.json:
            print(json.dumps({"status": "invalid", "error": getattr(exc, "code", "E_INPUT"),
                              "message": str(exc)}, ensure_ascii=False))
        else:
            print(f"B ask: {exc}", file=sys.stderr)
        return 1
    if args.json:
        output = _public(report)
        if texts is not None:
            output["revised"] = texts
            output["applied"] = bool(args.apply)
        print(json.dumps(output, ensure_ascii=False))
    else:
        for entry in report["declarations"]:
            print("\n".join(_render(entry)))
        if texts is not None:
            if args.apply:
                print("applied")
            else:
                print("revised source (use --apply to write it):")
                print(texts["file"] if not args.delta else texts["file"] + "--- " + str(args.delta) + "\n" + texts["delta"])
    if texts is not None:
        return 0
    return 2 if report["status"] == "question" else 0
