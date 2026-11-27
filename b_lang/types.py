"""B's explicit, conservative types, units, currencies, records and foreign signatures.

The checker allows limited numeric widening and nullable Option types. Dimensioned
types (Int[u], Float[u]) enforce unit and currency discipline statically so values
with different units or currencies cannot be mixed without explicit conversion.
Python ``Any`` is a dynamic boundary, NOT proof of static safety. Containers are
snapshotted by the runtime guard when crossing typed foreign boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Collection


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
BUILTIN_SEMANTIC_UNITS = frozenset({"utf8_bytes", "utf16_units", "codepoints"})


class BError(Exception):
    def __init__(self, code: str, message: str):
        self.code, self.message = code, message
        super().__init__(f"{code}: {message}")


def is_dim_int(typ: Type) -> bool:
    return typ.name == "Int" and len(typ.args) == 1


def is_dim_float(typ: Type) -> bool:
    return typ.name == "Float" and len(typ.args) == 1


def is_dim_numeric(typ: Type) -> bool:
    return is_dim_int(typ) or is_dim_float(typ)


def is_numeric(typ: Type) -> bool:
    return typ in (INT, FLOAT) or is_dim_numeric(typ)


def dim_of(typ: Type) -> str | None:
    return typ.args[0].name if is_dim_numeric(typ) else None


def base_numeric(typ: Type) -> Type:
    if typ.name == "Int":
        return INT
    if typ.name == "Float":
        return FLOAT
    return typ


def with_dim(base: Type, dim: str) -> Type:
    return Type(base.name, (Type(dim),))


def option(inner: Type) -> Type:
    if inner == NONE:
        return NONE
    if inner.name == "Option":
        return inner
    return Type("Option", (inner,))


def struct_record(fields: tuple[tuple[str, Type], ...] | list[tuple[str, Type]]) -> Type:
    return Type("Record", tuple(Type(name, (typ,)) for name, typ in fields))


def is_struct_record(typ: Type) -> bool:
    return typ.name == "Record" and bool(typ.args)


def struct_fields(typ: Type) -> tuple[tuple[str, Type], ...]:
    return tuple((f.name, f.args[0]) for f in typ.args)


def from_syntax(node, *, units: Collection[str] = (), records: Collection[str] = ()) -> Type:
    name, raw_args = node
    if name in ("Int", "Float") and len(raw_args) == 1:
        dim_name, dim_args = raw_args[0]
        if not dim_args and (dim_name in units or dim_name in BUILTIN_SEMANTIC_UNITS):
            return Type(name, (Type(dim_name),))
        if not dim_args and units:
            raise BError("E_UNIT", f"Unknown unit or currency {dim_name}")
    args = tuple(from_syntax(n, units=units, records=records) for n in raw_args)
    if name in KNOWN:
        if args:
            raise BError("E_TYPE", f"Type {name} has no type arguments")
        return KNOWN[name]
    if name in records:
        if args:
            raise BError("E_TYPE", f"Record type {name} has no type arguments")
        return Type(name)
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
    if actual == INT and expected == FLOAT:
        return True
    if is_dim_int(actual) and is_dim_float(expected) and actual.args == expected.args:
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
    if is_struct_record(actual) and is_struct_record(expected):
        af = dict(struct_fields(actual))
        ef = dict(struct_fields(expected))
        return set(af) == set(ef) and all(assignable(af[k], ef[k]) for k in ef)
    if is_struct_record(actual) and expected.name == "Dict" and expected.args[0] == TEXT:
        return all(assignable(ft, expected.args[1]) for _, ft in struct_fields(actual))
    return False


def unify(left: Type, right: Type) -> Type:
    if left == right:
        return left
    if ANY in (left, right):
        return ANY
    if {left, right} == {INT, FLOAT}:
        return FLOAT
    if is_dim_numeric(left) and is_dim_numeric(right) and left.args == right.args:
        return Type("Float", left.args)
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
    if is_struct_record(left) and is_struct_record(right):
        lf = dict(struct_fields(left))
        rf = dict(struct_fields(right))
        if set(lf) == set(rf):
            merged = []
            for k, lt in struct_fields(left):
                mt = unify(lt, rf[k])
                if mt == ANY and lt != ANY and rf[k] != ANY:
                    return ANY
                merged.append((k, mt))
            return struct_record(merged)
    if is_struct_record(left) and right.name == "Dict" and right.args[0] == TEXT:
        val_t = right.args[1]
        for _, ft in struct_fields(left):
            val_t = unify(val_t, ft)
        return Type("Dict", (TEXT, val_t))
    if is_struct_record(right) and left.name == "Dict" and left.args[0] == TEXT:
        return unify(right, left)
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


# Curated Python stdlib bindings; real stdlib stubs/discovery augment these.
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
    if is_struct_record(actual) and is_struct_record(expected):
        af = dict(struct_fields(actual))
        return any(needs_dynamic_guard(af[k], et) for k, et in struct_fields(expected) if k in af)
    if is_struct_record(actual) and expected.name == "Dict":
        return any(needs_dynamic_guard(ft, expected.args[1]) for _, ft in struct_fields(actual))
    return False


def needs_numeric_widening(actual: Type, expected: Type) -> bool:
    """Whether adopting a common type changes an integer's runtime value."""
    if expected.name == "Option":
        contained = actual.args[0] if actual.name == "Option" else actual
        return needs_numeric_widening(contained, expected.args[0])
    if actual.name == expected.name and actual.name in ("List", "Dict"):
        return needs_numeric_widening(actual.args[-1], expected.args[-1])
    if is_struct_record(actual) and is_struct_record(expected):
        af = dict(struct_fields(actual))
        return any(needs_numeric_widening(af[k], et) for k, et in struct_fields(expected) if k in af)
    if is_struct_record(actual) and expected.name == "Dict":
        return any(needs_numeric_widening(ft, expected.args[1]) for _, ft in struct_fields(actual))
    if is_dim_int(actual) and is_dim_float(expected) and actual.args == expected.args:
        return True
    return actual == INT and expected == FLOAT


def supports_ordering(typ: Type) -> bool:
    """Lists compare lexicographically. Dynamic operands defer to runtime."""
    while typ.name == "List":
        typ = typ.args[0]
    return typ in (BOOL, INT, FLOAT, TEXT, ANY) or is_dim_numeric(typ)


def parse_descriptor(text: str, *, allow_custom: bool = False) -> Type:
    """Parse trusted compiler-generated type descriptors without eval()."""
    import re
    parts = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\[|\]|,", text)
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
    if allow_custom:
        def build(node):
            name, raw_args = node
            if name in ("Int", "Float") and len(raw_args) == 1 and not raw_args[0][1]:
                return Type(name, (Type(raw_args[0][0]),))
            if name == "Record" and raw_args:
                fields = []
                for fname, fargs in raw_args:
                    if len(fargs) != 1:
                        raise BError("E_TYPE", f"Invalid Record field descriptor {fname}")
                    fields.append(Type(fname, (build(fargs[0]),)))
                return Type("Record", tuple(fields))
            args = tuple(build(c) for c in raw_args)
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
            if not args:
                return Type(name)
            raise BError("E_TYPE", f"Unknown type {name}")
        return build(parsed)
    return from_syntax(parsed)
