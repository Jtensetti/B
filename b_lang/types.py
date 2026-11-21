"""B's deliberately small and explicit static type lattice."""
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

def from_syntax(node) -> Type:
    name, raw_args = node
    if name not in KNOWN and name != "List":
        raise BError("E_TYPE", f"Unknown type {name}")
    args = tuple(from_syntax(n) for n in raw_args)
    if name == "List":
        if len(args) != 1: raise BError("E_TYPE", "List requires exactly one element type")
        return Type("List", args)
    if args: raise BError("E_TYPE", f"Type {name} has no type arguments")
    return KNOWN[name]

def assignable(actual: Type, expected: Type) -> bool:
    if expected == ANY or actual == ANY: return True
    if actual == expected: return True
    if actual == INT and expected == FLOAT: return True
    if actual.name == expected.name == "List":
        return assignable(actual.args[0], expected.args[0])
    return False

def unify(left: Type, right: Type) -> Type:
    if left == right: return left
    if ANY in (left, right): return ANY
    if {left, right} == {INT, FLOAT}: return FLOAT
    if left.name == right.name == "List": return Type("List", (unify(left.args[0], right.args[0]),))
    return ANY

@dataclass(frozen=True)
class Signature:
    params: tuple[Type, ...]
    result: Type

# Explicit, narrow signatures. Unlisted Python symbols remain dynamically checked.
# Manifest signatures describe the boundary but do NOT prove library internals.
BINDINGS: dict[str, Signature] = {
    "py:statistics.mean": Signature((Type("List", (FLOAT,)),), FLOAT),
    "py:math.sqrt": Signature((FLOAT,), FLOAT),
    "py:math.pow": Signature((FLOAT, FLOAT), FLOAT),
    "net:System.Math.Sqrt": Signature((FLOAT,), FLOAT),
    "net:System.Math.Pow": Signature((FLOAT, FLOAT), FLOAT),
    "net:System.Math.Abs": Signature((FLOAT,), FLOAT),
    "net:System.Math.Min": Signature((FLOAT, FLOAT), FLOAT),
    "net:System.Math.Max": Signature((FLOAT, FLOAT), FLOAT),
    "net:System.Text.RegularExpressions.Regex.IsMatch": Signature((TEXT, TEXT), BOOL),
}
ATTRIBUTES: dict[str, Type] = {"py:math.pi": FLOAT, "py:math.e": FLOAT}


def needs_dynamic_guard(actual: Type, expected: Type) -> bool:
    """True when dynamic portions of an otherwise assignable type need a runtime check."""
    if expected == ANY:
        return False
    if actual == ANY:
        return True
    if actual.name == expected.name == "List" and len(actual.args) == len(expected.args) == 1:
        return needs_dynamic_guard(actual.args[0], expected.args[0])
    return False
