"""`b ask`: find the booking an extended rule leaves ambiguous and ask about it.

For each `also` without `like`, B searches for the nearest input the rule
already covered (the precedent). If every function sharing an input name gives
the same result for the new case and the precedent, the context settles the
meaning and no question is needed. Otherwise B reports the first differing
outcome as a choice between two concrete values. One answer selects either
`keeping` for the functions that start the difference or `like` with a checked
repair of a repeated rule condition.
"""
from __future__ import annotations

from dataclasses import dataclass

from .compiler import compile_b
from .model import ToModel, parser_input, positioned_parser
from .precedent import (_functions, _reaches, call_text, causes, compare, literal, outcomes,
                        precedents, repeats_rule)
from .revision_witness import compare_functions, evaluate_scalar
from .types import BError


@dataclass
class _Span:
    origin: str  # "file" or "delta"
    start: int
    end: int


def _statements(text: str):
    tree = positioned_parser().parse(text)
    return list(zip(tree.children, ToModel().transform(tree), strict=True))


def _join(first: str, second: str | None) -> str:
    if not second:
        return first
    return first + ("" if first.endswith("\n") or not first else "\n") + second


def declaration_text(name, values, keeping, like) -> str:
    text = "also " + call_text(name, values)
    if like is not None:
        text += " like (" + ", ".join(literal(v) for v in like) + ")"
    if keeping:
        text += " keeping " + ", ".join(keeping)
    return text


def _body_span(node):
    expr = node.children[-1]
    meta = getattr(expr, "meta", None)
    if meta is None or getattr(meta, "empty", True):
        return None
    return meta.start_pos, meta.end_pos


class Session:
    def __init__(self, file_text: str, delta_text: str | None = None):
        self.texts = {"file": parser_input(file_text)}
        if delta_text is not None:
            self.texts["delta"] = parser_input(delta_text)
        self.parsed = {origin: _statements(text) for origin, text in self.texts.items()}

    def combined(self, texts=None) -> str:
        texts = texts or self.texts
        return _join(texts["file"], texts.get("delta"))

    def without(self, span: _Span) -> str:
        texts = dict(self.texts)
        text = texts[span.origin]
        texts[span.origin] = text[:span.start] + text[span.end:]
        return self.combined(texts)

    def declarations(self):
        for origin, rows in self.parsed.items():
            for node, statement in rows:
                if statement.kind == "also":
                    yield _Span(origin, node.meta.start_pos, node.meta.end_pos), statement

    def function(self, name: str):
        for origin, rows in self.parsed.items():
            for node, statement in rows:
                if statement.kind == "fn" and statement.parts[0] == name:
                    return origin, node
        return None


def _repair(session: Session, base, target: str, root: str):
    """Replace one textual copy of the rule's condition in `root` with a call."""
    functions = _functions(base.ir)
    rule = functions[target]
    if not repeats_rule(functions[root], rule.expr, rule.params):
        return None
    located_rule, located_root = session.function(target), session.function(root)
    if not located_rule or not located_root:
        return None
    rule_span = _body_span(located_rule[1])
    if rule_span is None:
        return None
    condition = session.texts[located_rule[0]][slice(*rule_span)]
    origin, node = located_root
    text = session.texts[origin]
    body = text[node.meta.start_pos:node.meta.end_pos]
    if body.count(condition) != 1:
        return None
    call = f"{target}({', '.join(n for n, _ in rule.params)})"
    offset = node.meta.start_pos + body.index(condition)
    return {"function": root, "origin": origin, "replace": condition, "with": call, "offset": offset}


def _edited(session: Session, repairs, span: _Span | None = None, declaration: str | None = None):
    """Apply repairs and optionally replace or remove one declaration, splicing from the end."""
    edits = [(r["origin"], r["offset"], len(r["replace"]), r["with"]) for r in repairs]
    if span is not None:
        edits.append((span.origin, span.start, span.end - span.start, declaration or ""))
    texts = dict(session.texts)
    for origin, offset, length, replacement in sorted(edits, key=lambda e: -e[1]):
        text = texts[origin]
        texts[origin] = text[:offset] + replacement + text[offset + length:]
    return texts


def _check_repair(repair, without_this) -> bool:
    """The rewrite must not change any result before the new rule case is added."""
    try:
        before = compile_b(without_this())
        after = compile_b(without_this([repair]))
    except BError:
        return False
    return compare_functions(before.optimized_ir, after.optimized_ir, [repair["function"]])["status"] == "proved"


def ask(file_text: str, delta_text: str | None = None) -> dict:
    session = Session(file_text, delta_text)
    after = compile_b(session.combined())
    questions = []
    for span, statement in session.declarations():
        target, new, keeping, like = statement.parts
        entry = {"declaration": declaration_text(target, new, keeping, like), "origin": span.origin}
        if like is not None:
            questions.append({**entry, "status": "checked", "reason": "like is checked during compilation"})
            continue

        def without_this(repairs=(), span=span):
            return session.combined(_edited(session, repairs, span))

        base = compile_b(without_this())
        known, prior = evaluate_scalar(base.ir, target, new)
        if known and prior is True:
            questions.append({**entry, "status": "no-change", "reason": f"{call_text(target, new)} was already true"})
            continue
        functions_after = _functions(after.ir)
        rule_params = [n for n, _ in functions_after[target].params]
        changes = []
        for name, fn in functions_after.items():
            if name == target or not fn.declared_pure or not fn.params:
                continue
            if not all(n in rule_params for n, _ in fn.params):
                continue
            args = tuple(new[rule_params.index(n)] for n, _ in fn.params)
            ok_before, value_before = evaluate_scalar(base.ir, name, args)
            ok_after, value_after = evaluate_scalar(after.ir, name, args)
            if ok_before and ok_after and (value_before != value_after or type(value_before) is not type(value_after)):
                changes.append({"function": name, "arguments": dict(zip((n for n, _ in fn.params), args)),
                                "before": value_before, "after": value_after})
        entry["changes"] = changes
        nearest = precedents(base.ir, target, new)
        if not nearest:
            questions.append({**entry, "status": "no-precedent",
                              "reason": f"B found no input on which {target} was already true"})
            continue
        precedent = nearest[0]
        entry["precedent"] = list(precedent)
        report = compare(after.ir, target, new, precedent)
        entry["uncompared"] = [{"function": n, "reason": r} for n, r in report.uncompared]
        roots = causes(after.ir, report.differences)
        open_roots = [r for r in roots if r not in keeping]
        like_text = declaration_text(target, new, keeping, precedent)
        if not report.differences:
            questions.append({**entry, "status": "settled", "suggestion": like_text,
                              "reason": f"{call_text(target, new)} now behaves like {call_text(target, precedent)}"})
            continue
        if not open_roots:
            questions.append({**entry, "status": "answered", "differences": [d.to_dict() for d in report.differences],
                              "reason": "keeping already names every function where the difference starts"})
            continue
        shown = outcomes(after.ir, report.differences)[0]
        outcome = next(d for d in report.differences if d.function == shown)
        keepable = [r for r in open_roots if not _reaches(functions_after, r, target)]
        keep_text = declaration_text(target, new, tuple(keeping) + tuple(keepable), None)
        repairs = []
        for root in open_roots:
            repair = _repair(session, base, target, root)
            if repair and _check_repair(repair, without_this):
                repairs.append(repair)
        repairs_complete = len(repairs) == len(open_roots)
        questions.append({
            **entry, "status": "question",
            "differences": [d.to_dict() for d in report.differences],
            "causes": open_roots,
            "outcome": outcome.to_dict(),
            "question": (f"{call_text(outcome.function, tuple(outcome.new_arguments.values()))}: "
                         f"{literal(outcome.new_value)} or {literal(outcome.precedent_value)}?"),
            "options": [
                {"value": outcome.new_value, "meaning": "as declared", "declaration": keep_text, "repairs": [],
                 "applicable": len(keepable) == len(open_roots)},
                {"value": outcome.precedent_value, "meaning": f"like {call_text(target, precedent)}",
                 "declaration": like_text, "applicable": repairs_complete,
                 "repairs": [{k: r[k] for k in ("function", "origin", "replace", "with")} for r in repairs]},
            ],
            "_repairs": repairs, "_span": span,
        })
    open_questions = [q for q in questions if q["status"] == "question"]
    return {"status": "question" if open_questions else "settled", "declarations": questions, "_session": session}


def parse_answer(text: str):
    from .model import parse
    try:
        statements = parse("also _(" + text + ")")
    except Exception as exc:
        raise BError("E_ANSWER", "Expected one B literal, for example 10, true or \"sun\"") from exc
    values = statements[0].parts[1]
    if len(values) != 1:
        raise BError("E_ANSWER", "Expected one B literal")
    return values[0]


def answer(report: dict, value) -> dict[str, str]:
    """Return the revised source texts for the selected option."""
    pending = [q for q in report["declarations"] if q["status"] == "question"]
    if len(pending) != 1:
        raise BError("E_ANSWER", f"Expected exactly one open question, found {len(pending)}")
    question = pending[0]
    choices = [o for o in question["options"]
               if type(o["value"]) is type(value) and o["value"] == value]
    if not choices:
        offered = " or ".join(literal(o["value"]) for o in question["options"])
        raise BError("E_ANSWER", f"The answer must be {offered}")
    option = choices[0]
    if not option["applicable"]:
        raise BError("E_ANSWER", f"B cannot write '{option['meaning']}' automatically: edit "
                     f"{', '.join(question['causes'])} so it agrees, then add {option['declaration']}")
    session = report["_session"]
    texts = _edited(session, question["_repairs"] if option["repairs"] else [], question["_span"],
                    option["declaration"])
    compile_b(session.combined(texts))  # the chosen meaning must compile, including like
    return texts
