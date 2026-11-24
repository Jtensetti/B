"""B's explicit, conservative types and foreign signature descriptions.

The checker allows limited numeric widening and nullable Option types. Python
``Any`` is a dynamic boundary, NOT proof of static safety. Containers are
snapshotted by the runtime guard when crossing typed foreign boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Type:
    name: str
    args: tuple["Type", ...] = ()

    def __str__(self):
        return self.name + ("[" + ", ".join(map(str, self.args)) + "]" if self.args else "")


INT = Type("Int")
FLOAT = Type("Float")
BOOL = Type("Bool")
TEXT = Type("Text")
NONE = Type("None")
ANY = Type("Any")
MODULE = Type("Module")
KNOWN = {t.name: t for t in (INT, FLOAT, BOOL, TEXT, NONE, ANY)}


class BError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")


def option(inner: Type) -> Type:
    if inner == NONE:
        return NONE
    if inner.name == "Option":
        return inner
    return Type("Option", (inner,))


# Named records declared by the program being compiled: name -> structural Type.
# A record is structural, as in TypeScript: Record[field[T], ...] with fields sorted.
RECORDS: dict[str, Type] = {}
# Named types for objects of another language, such as Python's datetime.date.
# B never looks inside them; it only calls their declared methods.
OPAQUE: dict[str, Type] = {}


def record_type(fields) -> Type:
    names = [n for n, _ in fields]
    if len(set(names)) != len(names):
        raise BError("E_TYPE", "A record names each field once")
    return Type("Record", tuple(Type(n, (t,)) for n, t in sorted(fields, key=lambda f: f[0])))


def record_fields(typ: Type) -> dict[str, Type]:
    return {field.name: field.args[0] for field in typ.args}


def from_syntax(node) -> Type:
    name, raw_args = node
    if name == "Record":
        return record_type([(field, from_syntax(inner[0])) for field, inner in raw_args])
    if name in RECORDS and not raw_args:
        return RECORDS[name]
    if name in OPAQUE and not raw_args:
        return OPAQUE[name]
    if name == "Opaque" and len(raw_args) == 1 and not raw_args[0][1]:
        return Type("Opaque", (Type(raw_args[0][0]),))
    args = tuple(from_syntax(n) for n in raw_args)
    if name in KNOWN:
        if args:
            raise BError("E_TYPE", f"Type {name} has no type arguments")
        return KNOWN[name]
    if name in ("List", "Option"):
        if len(args) != 1 or args[0] == NONE:
            raise BError("E_TYPE", f"{name} requires exactly one non-None element type")
        return Type(name, args)
    if name == "Dict":
        if len(args) != 2 or args[0] not in (TEXT,):
            raise BError("E_TYPE", "Dict requires exactly two arguments; keys must be Text")
        return Type(name, args)
    raise BError("E_TYPE", f"Unknown type {name}")


def assignable(actual: Type, expected: Type) -> bool:
    if expected == ANY or actual == ANY:
        return True
    if actual == expected:
        return True
    if actual.name == expected.name == "Record":
        have, want = record_fields(actual), record_fields(expected)
        # A missing optional field reads as none, so a record may leave it out.
        return set(have) <= set(want) and all(
            assignable(have[n], t) if n in have else t.name == "Option" for n, t in want.items())
    if actual == INT and expected == FLOAT:
        return True
    if expected.name == "Option":
        if actual == NONE:
            return True
        if actual.name == "Option":
            return assignable(actual.args[0], expected.args[0])
        return assignable(actual, expected.args[0])
    if actual.name == expected.name == "List":
        return assignable(actual.args[0], expected.args[0])
    if actual.name == expected.name == "Dict":
        return (actual.args[0] == expected.args[0]
                and assignable(actual.args[1], expected.args[1]))
    return False


def unify(left: Type, right: Type) -> Type:
    if left == right:
        return left
    if ANY in (left, right):
        return ANY
    if {left, right} == {INT, FLOAT}:
        return FLOAT
    if left == NONE:
        return option(right)
    if right == NONE:
        return option(left)
    if left.name == "Option" or right.name == "Option":
        a = left.args[0] if left.name == "Option" else left
        b = right.args[0] if right.name == "Option" else right
        inner = unify(a, b)
        return option(inner) if inner != ANY else ANY
    if left.name == right.name == "List":
        return Type("List", (unify(left.args[0], right.args[0]),))
    if left.name == right.name == "Dict" and left.args[0] == right.args[0]:
        return Type("Dict", (left.args[0], unify(left.args[1], right.args[1])))
    return ANY


@dataclass(frozen=True)
class Signature:
    params: tuple[Type, ...]
    result: Type
    min_arity: int | None = None

    @property
    def required(self) -> int:
        return len(self.params) if self.min_arity is None else self.min_arity


@dataclass(frozen=True)
class Overloads:
    """Explicit overload variants, NEVER an unchecked dynamic union."""
    options: tuple[Signature, ...]


Binding = Signature | Overloads


# Legacy hand-checked subset; real stdlib stubs may replace these in future.
BINDINGS: dict[str, Binding] = {
    "py:statistics.mean": Signature((Type("List", (FLOAT,)),), FLOAT),
    "py:math.sqrt": Signature((FLOAT,), FLOAT),
    "py:math.pow": Signature((FLOAT, FLOAT), FLOAT),
}
ATTRIBUTES: dict[str, Type] = {"py:math.pi": FLOAT, "py:math.e": FLOAT}


def needs_dynamic_guard(actual: Type, expected: Type) -> bool:
    if expected == ANY:
        return False
    if actual == ANY:
        return True
    if expected.name == "Option":
        if actual == NONE:
            return False
        return needs_dynamic_guard(
            actual.args[0] if actual.name == "Option" else actual,
            expected.args[0],
        )
    if actual.name == expected.name == "List":
        return needs_dynamic_guard(actual.args[0], expected.args[0])
    if actual.name == expected.name == "Dict":
        return needs_dynamic_guard(actual.args[1], expected.args[1])
    return False


def needs_numeric_widening(actual: Type, expected: Type) -> bool:
    """Whether adopting a common type changes an integer's runtime value."""
    if expected.name == "Option":
        contained = actual.args[0] if actual.name == "Option" else actual
        return needs_numeric_widening(contained, expected.args[0])
    if actual.name == expected.name and actual.name in ("List", "Dict"):
        return needs_numeric_widening(actual.args[-1], expected.args[-1])
    return actual == INT and expected == FLOAT


def supports_ordering(typ: Type) -> bool:
    """Lists compare lexicographically. Dynamic operands defer to runtime."""
    while typ.name == "List":
        typ = typ.args[0]
    return typ in (BOOL, INT, FLOAT, TEXT, ANY)


def parse_descriptor(text: str) -> Type:
    """Parse trusted compiler-generated type descriptors without eval()."""
    import re
    parts = re.findall(r"[^\W\d]\w*|\[|\]|,", text)
    if "".join(parts) != text.replace(" ", ""):
        raise BError("E_TYPE", "Invalid type descriptor")
    pos = 0

    def parse():
        nonlocal pos
        if pos >= len(parts) or not (parts[pos][0].isalpha() or parts[pos][0] == "_"):
            raise BError("E_TYPE", "Invalid type descriptor")
        name = parts[pos]
        pos += 1
        children = []
        if pos < len(parts) and parts[pos] == "[":
            pos += 1
            children.append(parse())
            while pos < len(parts) and parts[pos] == ",":
                pos += 1
                children.append(parse())
            if pos >= len(parts) or parts[pos] != "]":
                raise BError("E_TYPE", "Unclosed type descriptor")
            pos += 1
        return (name, tuple(children))

    parsed = parse()
    if pos != len(parts):
        raise BError("E_TYPE", "Unexpected type descriptor token")
    return from_syntax(parsed)
