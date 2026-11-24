"""One-shot source edits for the next maintainer. A pending edit has no runtime effect."""
from dataclasses import dataclass
from itertools import groupby

from .contracts import validate_predicate
from .ir import ExprIR, ProgramIR
from .model import parser_input, positioned_parser
from .types import ANY, BError


@dataclass(frozen=True)
class Handoff:
    instructions: tuple[str, ...]
    source: str
    target_spans: tuple[tuple[int, int], ...]

    def entries(self, original: str, *, include_context: bool = False) -> list[str]:
        if include_context:
            return [original[start:end] + "\n" + note for (start, end), note
                    in zip(self.target_spans, self.instructions, strict=True)]
        return list(self.instructions)


def materialize(source: str) -> Handoff:
    """Render all pending branches at their target bodies in the original lexical scope."""
    normalized = parser_input(source)
    tree = positioned_parser().parse(normalized)
    functions = {str(stmt.children[0]): stmt for stmt in tree.children if stmt.data == "fn_stmt"}
    instructions = []
    target_spans = []
    replacements = []
    targeted = set()
    for stmt in tree.children:
        if stmt.data != "next_stmt":
            continue
        name, condition, value = stmt.children
        if name not in functions:
            raise BError("E_HANDOFF", f"next requires a source function; no function named {name!r}")
        if name in targeted:
            raise BError("E_HANDOFF", f"Multiple next instructions for {name!r}; combine them into one")
        targeted.add(name)

        start, end = stmt.meta.start_pos, stmt.meta.end_pos
        instructions.append(source[start:end])
        line_start = normalized.rfind("\n", 0, start) + 1
        line_end = normalized.find("\n", end)
        replacements.append((line_start, len(source) if line_end == -1 else line_end + 1, ""))

        test = source[condition.meta.start_pos:condition.meta.end_pos]
        replacement = source[value.meta.start_pos:value.meta.end_pos]
        fn = functions[name]
        target_spans.append((fn.meta.start_pos, fn.meta.end_pos))
        body_start = fn.children[-1].meta.start_pos
        replacements.append((body_start, body_start, f"if {test} then {replacement} else "))

    pieces = []
    cursor = 0
    for start, end, replacement in sorted(replacements):
        pieces.extend((source[cursor:start], replacement))
        cursor = end
    pieces.append(source[cursor:])
    return Handoff(tuple(instructions), "".join(pieces), tuple(target_spans))


def _guard_chain(node: ExprIR):
    boundaries = []
    while node.op == "guard":
        if node.typ != ANY:
            boundaries.append(node.typ)
        node = node.operands[0]
    return boundaries, node


def _has_dynamic_values(typ):
    return typ == ANY or any(_has_dynamic_values(item) for item in typ.args)


def _same_value(old, new) -> bool:
    """Equal BIR, except that a name narrowed from Option[T] to T by a none test is the same value."""
    if old == new:
        return True
    if (old.op == new.op == "name" and old.data == new.data and old.typ.name == "Option"
            and old.typ.args[0] == new.typ):
        return True
    return (old.op == new.op and old.data == new.data and old.typ == new.typ
            and len(old.operands) == len(new.operands)
            and all(_same_value(a, b) for a, b in zip(old.operands, new.operands)))


def validate_rewrite(current: ProgramIR, revised: ProgramIR, targets, additional_cases=()):
    """Check the guard's effect boundary and preserve the previous fallback conversions."""
    before = {fn.name: fn for fn in current.statements if fn.op == "fn"}
    after = {fn.name: fn for fn in revised.statements if fn.op == "fn"}
    for name in targets:
        old_guards, old_value = _guard_chain(before[name].expr)
        new_guards, decision = _guard_chain(after[name].expr)
        if name in additional_cases:
            # Persistent facts are already checked for both programs. next
            # rewrites the original source body beneath that same outer test.
            if old_value.op != "conditional" or decision.op != "conditional" or (
                    old_value.operands[:2] != decision.operands[:2]):
                raise BError("E_HANDOFF", f"next would alter the also cases of {name}")
            under_old, old_value = _guard_chain(old_value.operands[2])
            under_new, decision = _guard_chain(decision.operands[2])
            old_guards += under_old
            new_guards += under_new
        test, _, fallback = decision.operands
        params = {n for n, typ in after[name].params if not _has_dynamic_values(typ)}
        try:
            validate_predicate(test, params)
        except BError as exc:
            raise BError("E_HANDOFF", f"Guard for {name} must use a contract predicate over statically "
                         f"typed parameters: {exc.message}") from exc

        # Typed conditionals can widen an integer to float or add a dynamic
        # guard even on the old branch. The same return guard twice is idempotent.
        fallback_guards, fallback_value = _guard_chain(fallback)
        old_types = [typ for typ, _ in groupby(old_guards)]
        new_types = [typ for typ, _ in groupby(new_guards + fallback_guards)]
        if old_types != new_types or not _same_value(old_value, fallback_value):
            raise BError("E_HANDOFF", f"next would change the existing fallback's conversion in {name}; "
                         "use a replacement compatible with its current return path")


def inspect_handoff(source: str, *, strict: bool = False, include_context: bool = False) -> tuple[list[str], str]:
    """Validate the program and proposed revision, without running either."""
    from .compiler import compile_b

    handoff = compile_b(source, strict=strict).handoff
    if handoff is None:
        return [], source
    return handoff.entries(source, include_context=include_context), handoff.source
