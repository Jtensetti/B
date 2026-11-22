"""File and command-line interfaces for finite contract questions."""
import json
import sys
from pathlib import Path

from .types import BError


MAX_REQUEST_BYTES = 64 * 1024


def add_command(sub):
    command = sub.add_parser("clarify", help="Compare possible contracts on an explicit finite domain")
    command.add_argument("file", type=Path, help="B source containing the original interface")
    command.add_argument("request", type=Path, help="JSON with function, candidates, axes and outputs")
    command.add_argument("--answer", action="append", default=[], metavar="JSON",
                         help='Repeatable response, e.g. {"inputs":{"rank":0},"result":2,"allowed":true}')
    command.add_argument("--edit", type=Path, help="Ask only what matters to a proposed B revision")
    command.add_argument("--strategy", choices=("balanced", "minimax"),
                         help="Question strategy for identifying a policy")
    command.add_argument("--json", action="store_true", help="Emit the full finite-domain report")


def _json(text):
    def object_from_pairs(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise BError("E_CLARIFY_INPUT", f"Duplicate JSON key {key!r}")
            obj[key] = value
        return obj
    try:
        return json.loads(text, object_pairs_hook=object_from_pairs)
    except (ValueError, RecursionError) as exc:
        raise BError("E_CLARIFY_INPUT", f"Invalid JSON: {exc}") from exc


def _fields(value, required, optional=()):
    if not isinstance(value, dict):
        raise BError("E_CLARIFY_INPUT", "Expected a JSON object")
    missing = set(required) - set(value)
    extra = set(value) - set(required) - set(optional)
    if missing or extra:
        raise BError("E_CLARIFY_INPUT", f"Missing fields {sorted(missing)}, unexpected fields {sorted(extra)}")


def load_request(path, extra_answers):
    with path.open("rb") as stream:
        raw = stream.read(MAX_REQUEST_BYTES + 1)
    if len(raw) + sum(len(a.encode("utf-8")) for a in extra_answers) > MAX_REQUEST_BYTES:
        raise BError("E_CLARIFY_LIMIT", f"Request and responses exceed {MAX_REQUEST_BYTES} bytes")
    request = _json(raw)
    _fields(request, ("function", "candidates", "axes", "outputs"), ("answers",))
    if not isinstance(request["function"], str) or not request["function"].isidentifier():
        raise BError("E_CLARIFY_INPUT", "Expected a B function name")
    responses = request.get("answers", [])
    if not isinstance(responses, list):
        raise BError("E_CLARIFY_INPUT", "Expected answers to be an array of objects")
    answers = []
    for record in [*responses, *(_json(text) for text in extra_answers)]:
        _fields(record, ("inputs", "result", "allowed"))
        answers.append((record["inputs"], record["result"], record["allowed"]))
    return request, answers


def run(args, compile_file):
    try:
        if args.edit and args.strategy:
            raise BError("E_CLARIFY_INPUT", "--strategy applies to policy identification. --edit selects questions about revised outputs.")
        request, answers = load_request(args.request, args.answer)
        base = compile_file(args.file).ir
        common = (request["function"], request["candidates"], request["axes"], request["outputs"], answers)
        if args.edit:
            from .edit_clarification import decide_edit
            data = decide_edit(base, compile_file(args.edit).ir, *common)
        else:
            from .clarification import compare
            data = compare(base, *common, strategy=args.strategy or "balanced")
    except (BError, OSError, ValueError, RuntimeError) as exc:
        if args.json:
            print(json.dumps({"status": "error", "error": {"code": getattr(exc, "code", "E_INPUT"), "message": str(exc)}}))
        else:
            print(f"B clarify: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(data, ensure_ascii=False))
    else:
        subject = "revised outputs against remaining policies" if args.edit else "candidate policies"
        print(f"{request['function']} — {data['status']} ({subject} on this grid)")
        if data.get("reason"):
            print(data["reason"])
        plan = data.get("planning")
        if plan and plan["used"] == "balanced":
            print("Using a balanced split because exact planning exceeded its limit.")
        elif plan and plan["worst_case_remaining_questions"] is not None:
            depth = plan["worst_case_remaining_questions"]
            print(f"At most {depth} more definite answer(s) to distinguish the listed behaviors on this grid.")
        elif plan and plan["full_class_identification_possible"] is False:
            print("Some remaining behaviors differ only on skipped questions.")
        question = data.get("question")
        if question:
            inputs = ", ".join(f"{key}={value}" for key, value in question["inputs"].items())
            print(f"May {request['function']}({inputs}) return {question['result']}?")
            print("Would allow:", ", ".join(question["allowed_by"]))
            print("Would forbid:", ", ".join(question["forbidden_by"]))
        elif data.get("survivors"):
            print("Remaining policies:", ", ".join(data["survivors"]))
    if args.edit:
        if data["status"] == "approve":
            return 0
        return 1 if data["status"] == "reject" else 2
    return 2 if data["status"] in {"inconsistent", "undetermined", "empty-domain"} else 0
