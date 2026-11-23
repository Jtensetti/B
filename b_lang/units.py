"""Quantities with units: relations that are always the same.

A kilometer is always 1000 meters. An inch is always 25.4 millimeters, an
hour 3600 seconds and a kilowatt-hour 3.6 megajoules. B knows these relations,
checks the dimension of every quantity expression before the program runs and
erases the units afterwards: every quantity is a Float in its SI base unit.

What B deliberately does not know: exchange rates, which change; the length
of a month or a year, which varies; and which country's "kr" is meant. `kr`
is Swedish kronor in B. Norwegian and Danish kroner are written NOK and DKK.
Each currency is its own dimension, so SEK and USD only meet through a rate
the program states.

Absolute temperatures (`K`, `degC`, `degF`) are affine. Two of them cannot be
added. Their difference is a temperature difference (`dK`, `dC`, `dF`).
"""
from __future__ import annotations

from fractions import Fraction as F
from math import pi

from .model import Expr, Stmt
from .types import BError

Dim = tuple  # sorted ((base, exponent), ...); () is a plain number

CURRENCIES = {
    "SEK": "Swedish krona", "NOK": "Norwegian krone", "DKK": "Danish krone", "ISK": "Icelandic króna",
    "EUR": "euro", "USD": "United States dollar", "GBP": "pound sterling", "CHF": "Swiss franc",
    "JPY": "Japanese yen", "CNY": "Chinese yuan", "INR": "Indian rupee", "CAD": "Canadian dollar",
    "AUD": "Australian dollar", "NZD": "New Zealand dollar", "PLN": "Polish złoty", "CZK": "Czech koruna",
    "HUF": "Hungarian forint", "BRL": "Brazilian real", "MXN": "Mexican peso", "ZAR": "South African rand",
    "KRW": "South Korean won", "SGD": "Singapore dollar", "HKD": "Hong Kong dollar", "TRY": "Turkish lira",
}


def dim(**exponents) -> Dim:
    return tuple(sorted((k, v) for k, v in exponents.items() if v))


def _combine(a: Dim, b: Dim, sign: int) -> Dim:
    total = dict(a)
    for base, exp in b:
        total[base] = total.get(base, 0) + sign * exp
    return tuple(sorted((k, v) for k, v in total.items() if v))


LENGTH, MASS, TIME = dim(m=1), dim(kg=1), dim(s=1)
TEMPERATURE = dim(Tabs=1)  # an absolute temperature, stored in kelvin
DELTA_T = dim(K=1)

# name -> (factor to the base unit, dimension, offset of an absolute scale)
UNITS: dict[str, tuple[F, Dim, F]] = {}


def _unit(names, factor, dimension, offset=F(0)):
    for name in names.split():
        if name in UNITS:
            raise ValueError(f"duplicate unit {name}")
        UNITS[name] = (F(factor), dimension, F(offset))


_unit("m", 1, LENGTH)
_unit("km", 1000, LENGTH)
_unit("dm", F(1, 10), LENGTH)
_unit("cm", F(1, 100), LENGTH)
_unit("mm", F(1, 1000), LENGTH)
_unit("um", F(1, 10**6), LENGTH)
_unit("nm", F(1, 10**9), LENGTH)
_unit("mil", 10000, LENGTH)  # the Swedish mil, exactly 10 km since 1889
_unit("inch", F(254, 10000), LENGTH)
_unit("ft", F(3048, 10000), LENGTH)
_unit("yd", F(9144, 10000), LENGTH)
_unit("mi", F(1609344, 1000), LENGTH)
_unit("nmi", 1852, LENGTH)
_unit("au", 149597870700, LENGTH)

_unit("kg", 1, MASS)
_unit("g", F(1, 1000), MASS)
_unit("mg", F(1, 10**6), MASS)
_unit("ug", F(1, 10**9), MASS)
_unit("t", 1000, MASS)
_unit("hg", F(1, 10), MASS)  # hekto, as on Swedish price labels
_unit("lb", F(45359237, 10**8), MASS)
_unit("oz", F(45359237, 16 * 10**8), MASS)

_unit("s", 1, TIME)
_unit("ms", F(1, 1000), TIME)
_unit("us", F(1, 10**6), TIME)
_unit("ns", F(1, 10**9), TIME)
_unit("min", 60, TIME)
_unit("h", 3600, TIME)
_unit("day", 86400, TIME)  # a duration of 24 hours, not a calendar day
_unit("week", 604800, TIME)

_unit("m2", 1, dim(m=2))
_unit("cm2", F(1, 10**4), dim(m=2))
_unit("mm2", F(1, 10**6), dim(m=2))
_unit("km2", 10**6, dim(m=2))
_unit("ha", 10**4, dim(m=2))
_unit("m3", 1, dim(m=3))
_unit("cm3", F(1, 10**6), dim(m=3))
_unit("l", F(1, 1000), dim(m=3))
_unit("dl", F(1, 10**4), dim(m=3))
_unit("cl", F(1, 10**5), dim(m=3))
_unit("ml", F(1, 10**6), dim(m=3))
_unit("gal", F(3785411784, 10**12), dim(m=3))  # US liquid gallon

_unit("mph", F(1609344, 3600000), dim(m=1, s=-1))
_unit("knot", F(1852, 3600), dim(m=1, s=-1))
_unit("Hz", 1, dim(s=-1))
_unit("kHz", 1000, dim(s=-1))
_unit("MHz", 10**6, dim(s=-1))
_unit("GHz", 10**9, dim(s=-1))
_unit("rpm", F(1, 60), dim(s=-1))

_unit("N", 1, dim(kg=1, m=1, s=-2))
_unit("kN", 1000, dim(kg=1, m=1, s=-2))
_unit("J", 1, dim(kg=1, m=2, s=-2))
_unit("kJ", 1000, dim(kg=1, m=2, s=-2))
_unit("MJ", 10**6, dim(kg=1, m=2, s=-2))
_unit("Wh", 3600, dim(kg=1, m=2, s=-2))
_unit("kWh", 3600000, dim(kg=1, m=2, s=-2))
_unit("MWh", 3600 * 10**6, dim(kg=1, m=2, s=-2))
_unit("cal", F(4184, 1000), dim(kg=1, m=2, s=-2))  # thermochemical calorie
_unit("kcal", 4184, dim(kg=1, m=2, s=-2))
_unit("W", 1, dim(kg=1, m=2, s=-3))
_unit("kW", 1000, dim(kg=1, m=2, s=-3))
_unit("MW", 10**6, dim(kg=1, m=2, s=-3))
_unit("hp", F(73549875, 10**5), dim(kg=1, m=2, s=-3))  # metric horsepower
_unit("Pa", 1, dim(kg=1, m=-1, s=-2))
_unit("hPa", 100, dim(kg=1, m=-1, s=-2))
_unit("kPa", 1000, dim(kg=1, m=-1, s=-2))
_unit("bar", 10**5, dim(kg=1, m=-1, s=-2))
_unit("atm", 101325, dim(kg=1, m=-1, s=-2))

_unit("A", 1, dim(A=1))
_unit("mA", F(1, 1000), dim(A=1))
_unit("C", 1, dim(A=1, s=1))
_unit("mAh", F(36, 10), dim(A=1, s=1))
_unit("V", 1, dim(kg=1, m=2, s=-3, A=-1))
_unit("mV", F(1, 1000), dim(kg=1, m=2, s=-3, A=-1))
_unit("kV", 1000, dim(kg=1, m=2, s=-3, A=-1))
_unit("ohm", 1, dim(kg=1, m=2, s=-3, A=-2))
_unit("mol", 1, dim(mol=1))
_unit("cd", 1, dim(cd=1))

_unit("bit", 1, dim(bit=1))
_unit("kbit", 1000, dim(bit=1))
_unit("Mbit", 10**6, dim(bit=1))
_unit("Gbit", 10**9, dim(bit=1))
_unit("B", 8, dim(bit=1))
_unit("kB", 8 * 10**3, dim(bit=1))
_unit("MB", 8 * 10**6, dim(bit=1))
_unit("GB", 8 * 10**9, dim(bit=1))
_unit("TB", 8 * 10**12, dim(bit=1))
_unit("KiB", 8 * 2**10, dim(bit=1))
_unit("MiB", 8 * 2**20, dim(bit=1))
_unit("GiB", 8 * 2**30, dim(bit=1))
_unit("TiB", 8 * 2**40, dim(bit=1))

_unit("rad", 1, dim(rad=1))
_unit("deg", F(pi) / 180, dim(rad=1))  # pi is rounded to the nearest Float
_unit("turn", 2 * F(pi), dim(rad=1))

_unit("K", 1, TEMPERATURE)
_unit("degC", 1, TEMPERATURE, F(27315, 100))
_unit("degF", F(5, 9), TEMPERATURE, F(27315, 100) - F(32) * F(5, 9))
_unit("dK", 1, DELTA_T)
_unit("dC", 1, DELTA_T)
_unit("dF", F(5, 9), DELTA_T)

for _code in CURRENCIES:
    _unit(_code, 1, dim(**{_code: 1}))
_unit("kr", 1, dim(SEK=1))
_unit("öre", F(1, 100), dim(SEK=1))
_unit("cent", F(1, 100), dim(EUR=1))  # euro cent; a US cent is written 0.01 USD

DIMENSION_TYPES = {
    "Length": LENGTH, "Mass": MASS, "Duration": TIME, "Area": dim(m=2), "Volume": dim(m=3),
    "Speed": dim(m=1, s=-1), "Acceleration": dim(m=1, s=-2), "Frequency": dim(s=-1),
    "Force": dim(kg=1, m=1, s=-2), "Energy": dim(kg=1, m=2, s=-2), "Power": dim(kg=1, m=2, s=-3),
    "Pressure": dim(kg=1, m=-1, s=-2), "Current": dim(A=1), "Charge": dim(A=1, s=1),
    "Voltage": dim(kg=1, m=2, s=-3, A=-1), "Resistance": dim(kg=1, m=2, s=-3, A=-2),
    "Data": dim(bit=1), "DataRate": dim(bit=1, s=-1), "Angle": dim(rad=1), "Density": dim(kg=1, m=-3),
    "Temperature": TEMPERATURE, "TemperatureDifference": DELTA_T, "Amount": dim(mol=1),
    # Swedish names for the most common ones.
    "Längd": LENGTH, "Sträcka": LENGTH, "Massa": MASS, "Vikt": MASS, "Tid": TIME,
    "Yta": dim(m=2), "Volym": dim(m=3), "Hastighet": dim(m=1, s=-1), "Energi": dim(kg=1, m=2, s=-2),
    "Effekt": dim(kg=1, m=2, s=-3), "Tryck": dim(kg=1, m=-1, s=-2), "Temperatur": TEMPERATURE,
}


# Vocabulary borrowed from a relative. B's own table always wins; a name it
# lacks is looked up in pint when pint is installed. Each borrowed unit is
# reported as an assumption, like any other foreign metadata.
_PINT_BASES = {"[length]": "m", "[mass]": "kg", "[time]": "s", "[current]": "A",
               "[substance]": "mol", "[luminosity]": "cd", "[information]": "bit"}
_vocabulary = None
BORROWED: dict[str, str] = {}  # unit name -> provenance, for the current compilation


def use_vocabulary(registry, provenance: str = "pint") -> None:
    """Install a pint-compatible registry (tests use a small stand-in)."""
    global _vocabulary
    _vocabulary = (registry, provenance) if registry is not None else False


def _registry():
    global _vocabulary
    if _vocabulary is None:
        try:
            import pint
            _vocabulary = (pint.UnitRegistry(), f"pint {pint.__version__}")
        except Exception:  # not installed, or failed to load: B's own table only
            _vocabulary = False
    return _vocabulary or None


def borrowed(name: str) -> tuple[F, Dim, F] | None:
    found = _registry()
    if found is None:
        return None
    registry, provenance = found
    try:
        base = registry.Quantity(1, name).to_base_units()
        dimensionality = dict(base.dimensionality)
        magnitude = base.magnitude
    except Exception:
        return None
    exponents = {}
    for key, power in dimensionality.items():
        if key not in _PINT_BASES or power != int(power):
            return None  # temperatures and unknown dimensions stay with B's own table
        exponents[_PINT_BASES[key]] = int(power)
    try:
        factor = F(str(magnitude))
    except (TypeError, ValueError):
        return None
    if factor <= 0:
        return None
    BORROWED[name] = provenance
    return factor, dim(**exponents), F(0)


def _lookup(name: str) -> tuple[F, Dim, F]:
    if name in UNITS:
        return UNITS[name]
    found = borrowed(name)
    if found is None:
        raise BError("E_UNIT", f"Unknown unit {name!r}" + _suggest(name))
    return found


def unit_of(spec) -> tuple[F, Dim, F]:
    name, per = spec
    factor, dimension, offset = _lookup(name)
    if per is None:
        return factor, dimension, offset
    other, below, other_offset = _lookup(per)
    if offset or other_offset:
        raise BError("E_UNIT", "An absolute temperature cannot be part of 'per'; use dK, dC or dF")
    return factor / other, _combine(dimension, below, -1), F(0)


def _suggest(name: str) -> str:
    hints = {"in": "inch", "°C": "degC", "C°": "degC", "sek": "SEK", "usd": "USD", "month": None,
             "year": None, "månad": None, "år": None, "d": "day", "hr": "h", "sec": "s", "lbs": "lb"}
    if name in hints and hints[name]:
        return f"; did you mean {hints[name]}?"
    if name in hints:
        return "; months and years have no fixed length. Count days, or use calendar functions"
    return ""


def describe(dimension: Dim) -> str:
    if not dimension:
        return "a plain number"
    for label, value in DIMENSION_TYPES.items():
        if value == dimension and label.isascii():
            return label
    if len(dimension) == 1 and dimension[0][1] == 1 and dimension[0][0] in CURRENCIES:
        return f"Money[{dimension[0][0]}]"
    top = " * ".join(b if e == 1 else f"{b}^{e}" for b, e in dimension if e > 0) or "1"
    bottom = " * ".join(b if e == -1 else f"{b}^{-e}" for b, e in dimension if e < 0)
    return top + (f" per {bottom}" if bottom else "")


def type_dimension(syntax) -> Dim | None:
    """The dimension a declared type stands for, or None for an ordinary type."""
    name, args = syntax
    if name in DIMENSION_TYPES and not args:
        return DIMENSION_TYPES[name]
    if name in DIMENSION_TYPES:
        boundary_unit(syntax)  # validates Length[ft]
        return DIMENSION_TYPES[name]
    if name in ("Money", "Pengar"):
        if len(args) != 1 or args[0][0] not in CURRENCIES or args[0][1]:
            raise BError("E_UNIT", f"{name} needs one currency code, for example {name}[SEK]")
        return dim(**{args[0][0]: 1})
    if name in ("Rate", "Kurs"):
        if len(args) != 2 or any(a[0] not in CURRENCIES or a[1] for a in args):
            raise BError("E_UNIT", f"{name} needs two currency codes: {name}[SEK, USD] is SEK per USD")
        return dim(**{args[0][0]: 1, args[1][0]: -1}) if args[0][0] != args[1][0] else ()
    for arg in args:
        if type_dimension(arg) is not None:
            raise BError("E_UNIT", f"Quantities inside {name} are not supported yet; convert with 'as'")
    return None


def boundary_unit(syntax) -> tuple[F, Dim, F] | None:
    """The unit a foreign value is expressed in: Length[ft] is a length in feet."""
    name, args = syntax
    if name in DIMENSION_TYPES and args:
        if len(args) != 1 or args[0][1]:
            raise BError("E_UNIT", f"{name}[...] takes one unit name, for example {name}[m]")
        factor, dimension, offset = unit_of((args[0][0], None))
        if dimension != DIMENSION_TYPES[name]:
            raise BError("E_UNIT", f"{args[0][0]} measures {describe(dimension)}, not {name}")
        return factor, dimension, offset
    if name in ("Money", "Pengar", "Rate", "Kurs"):
        dimension = type_dimension(syntax)
        return F(1), dimension, F(0)
    return None


def _base_name(dimension: Dim) -> str:
    for name, (factor, d, offset) in UNITS.items():
        if d == dimension and factor == 1 and not offset:
            return name
    return "unit"


def _dotted(node) -> str | None:
    if isinstance(node, Expr) and node.kind == "name":
        return node.parts[0]
    if isinstance(node, Expr) and node.kind == "attr":
        base = _dotted(node.parts[0])
        return None if base is None else f"{base}.{node.parts[1]}"
    return None


FLOAT_SYNTAX = ("Float", ())


def _float(value: F) -> Expr:
    return Expr("literal", (float(value),))


def _is_zero(node: Expr) -> bool:
    return node.kind == "literal" and type(node.parts[0]) in (int, float) and node.parts[0] == 0


class _Checker:
    """Check dimensions. Fold quantities known at compile time with exact fractions."""

    def __init__(self, signatures: dict[str, tuple[list[Dim | None], Dim | None]], foreign=None):
        self.signatures = signatures
        self.foreign = foreign or {}  # "alias.member" -> ([unit or None per parameter], unit or None)
        # id of a rewritten literal -> (that literal, its exact value). The node is kept so its
        # id cannot be reused by another object; identity is checked on every lookup.
        self.exact: dict[int, tuple[Expr, F]] = {}
        self.bound: dict[str, F] = {}  # top-level bindings with an exact value

    def known(self, node, original=None) -> F | None:
        entry = self.exact.get(id(node))
        if entry is not None and entry[0] is node:
            return entry[1]
        source = original if original is not None else node
        if isinstance(source, Expr) and source.kind == "literal" and type(source.parts[0]) in (int, float):
            return F(str(source.parts[0])) if type(source.parts[0]) is float else F(source.parts[0])
        if isinstance(source, Expr) and source.kind == "name" and source.parts[0] in self.bound:
            return self.bound[source.parts[0]]
        return None

    def _is_exact(self, node) -> bool:
        entry = self.exact.get(id(node))
        return entry is not None and entry[0] is node

    def literal(self, value: F) -> Expr:
        node = _float(value)
        self.exact[id(node)] = (node, value)
        return node

    def border_call(self, path, target, arguments, env):
        """Convert B's SI values to the units a foreign function expects, and back."""
        expected, result = self.foreign[path]
        rewritten = []
        for index, argument in enumerate(arguments):
            value, dimension = self.expr(argument, env)
            spec = expected[index] if index < len(expected) else None
            if spec is None:
                if dimension:
                    raise BError("E_UNIT", f"Argument {index + 1} of {path} is a plain number, "
                                 f"got {describe(dimension)}")
                rewritten.append(value)
                continue
            factor, wanted, offset = spec
            if dimension != wanted and not (_is_zero(argument) and wanted):
                raise BError("E_UNIT", f"Argument {index + 1} of {path} must be {describe(wanted)}, "
                             f"got {describe(dimension)}")
            known = self.known(value, argument)
            if known is not None:
                rewritten.append(self.literal((known - offset) / factor))
            else:
                if offset:
                    value = Expr("sub", (value, _float(offset)))
                rewritten.append(value if factor == 1 else Expr("div", (value, _float(factor))))
        call = Expr("invoke", (target, tuple(rewritten)))
        if result is None:
            return call, ()
        factor, dimension, offset = result
        if factor != 1:
            call = Expr("mul", (call, _float(factor)))
        if offset:
            call = Expr("add", (call, _float(offset)))
        return call, dimension

    def fold(self, kind, a, b, parts, dimension):
        """Compute a quantity expression exactly when both operands are known."""
        left, right = self.known(a, parts[0]), self.known(b, parts[1])
        if dimension is None or left is None or right is None or (kind == "div" and right == 0):
            return Expr(kind, (a, b))
        if not (self._is_exact(a) or self._is_exact(b) or dimension):
            return Expr(kind, (a, b))
        ops = {"add": lambda x, y: x + y, "sub": lambda x, y: x - y,
               "mul": lambda x, y: x * y, "div": lambda x, y: x / y}
        return self.literal(ops[kind](left, right))

    def plain(self, node, env, context: str):
        rewritten, dimension = self.expr(node, env)
        if dimension:
            raise BError("E_UNIT", f"{context} needs a plain number, got {describe(dimension)}; "
                         "convert it with 'as', for example 'as km'")
        return rewritten

    def same(self, left, right, env, what: str):
        a, da = self.expr(left, env)
        b, db = self.expr(right, env)
        if da != db:
            if _is_zero(left) and db:
                return a, b, db
            if _is_zero(right) and da:
                return a, b, da
            raise BError("E_UNIT", f"Cannot {what} {describe(da)} and {describe(db)}")
        return a, b, da

    def expr(self, node, env: dict) -> tuple[object, Dim]:
        if not isinstance(node, Expr):
            return node, ()
        kind, parts = node.kind, node.parts
        if kind == "quantity":
            value, spec = parts
            factor, dimension, offset = unit_of(spec)
            return self.literal(F(str(value)) * factor + offset), dimension
        if kind == "neg" and isinstance(parts[0], Expr) and parts[0].kind == "quantity":
            value, spec = parts[0].parts
            factor, dimension, offset = unit_of(spec)
            return self.literal(-F(str(value)) * factor + offset), dimension
        if kind == "convert":
            inner, dimension = self.expr(parts[0], env)
            factor, wanted, offset = unit_of(parts[1])
            if dimension != wanted:
                raise BError("E_UNIT", f"Cannot express {describe(dimension)} in {parts[1][0]}"
                             + (f" per {parts[1][1]}" if parts[1][1] else "")
                             + f", which measures {describe(wanted)}")
            value = self.known(inner, parts[0])
            if value is not None:
                return self.literal((value - offset) / factor), ()
            if offset:
                inner = Expr("sub", (inner, _float(offset)))
            return (inner if factor == 1 else Expr("div", (inner, _float(factor)))), ()
        if kind == "name":
            return node, env.get(parts[0], ())
        if kind == "literal":
            return node, ()
        if kind in ("add", "sub"):
            a, da = self.expr(parts[0], env)
            b, db = self.expr(parts[1], env)
            if TEMPERATURE in (da, db) and da != db or (da == db == TEMPERATURE):
                result = {("add", TEMPERATURE, DELTA_T): TEMPERATURE, ("add", DELTA_T, TEMPERATURE): TEMPERATURE,
                          ("sub", TEMPERATURE, DELTA_T): TEMPERATURE,
                          ("sub", TEMPERATURE, TEMPERATURE): DELTA_T}.get((kind, da, db))
                if result is None:
                    raise BError("E_UNIT", f"Cannot {'add' if kind == 'add' else 'subtract'} "
                                 f"{describe(da)} and {describe(db)}; two absolute temperatures only "
                                 "have a difference, written in dK, dC or dF")
                return self.fold(kind, a, b, parts, result), result
            a, b, dimension = self.same(parts[0], parts[1], env, "add" if kind == "add" else "subtract")
            return self.fold(kind, a, b, parts, dimension), dimension
        if kind in ("mul", "div"):
            a, da = self.expr(parts[0], env)
            b, db = self.expr(parts[1], env)
            if TEMPERATURE in (da, db):
                raise BError("E_UNIT", "An absolute temperature cannot be multiplied or divided; "
                             "convert it with 'as K' first")
            dimension = _combine(da, db, 1 if kind == "mul" else -1)
            return self.fold(kind, a, b, parts, dimension if (da or db) else None), dimension
        if kind == "mod":
            a, b, dimension = self.same(parts[0], parts[1], env, "take the remainder of")
            return Expr(kind, (a, b)), dimension
        if kind == "neg":
            a, dimension = self.expr(parts[0], env)
            if dimension == TEMPERATURE:
                raise BError("E_UNIT", "Negate a temperature literal directly, for example -5 degC")
            return Expr(kind, (a,)), dimension
        if kind == "cmp":
            left, op, right = parts
            a, b, _ = self.same(left, right, env, "compare")
            return Expr(kind, (a, op, b)), ()
        if kind == "conditional":
            test = self.plain(parts[0], env, "A condition")
            a, b, dimension = self.same(parts[1], parts[2], env, "choose between")
            return Expr(kind, (test, a, b)), dimension
        if kind == "coalesce":
            a, b, dimension = self.same(parts[0], parts[1], env, "combine with ??")
            return Expr(kind, (a, b)), dimension
        if kind in ("and", "or", "not"):
            return Expr(kind, tuple(self.plain(p, env, f"'{kind}'") for p in parts)), ()
        if kind == "invoke":
            target, arguments = parts
            if isinstance(target, Expr) and target.kind == "name" and target.parts[0] in self.signatures:
                name = target.parts[0]
                expected, result = self.signatures[name]
                rewritten = []
                for index, argument in enumerate(arguments):
                    value, dimension = self.expr(argument, env)
                    wanted = expected[index] if index < len(expected) else None
                    if (wanted or ()) != dimension and not (_is_zero(argument) and wanted):
                        raise BError("E_UNIT", f"Argument {index + 1} of {name} must be "
                                     f"{describe(wanted or ())}, got {describe(dimension)}")
                    rewritten.append(value)
                return Expr(kind, (target, tuple(rewritten))), result or ()
            path = _dotted(target)
            if path in self.foreign:
                return self.border_call(path, target, arguments, env)
            target = self._children(target, env, "A called value")
            return Expr(kind, (target, tuple(self.plain(a, env, "An argument to a foreign or computed call")
                                             for a in arguments))), ()
        if kind == "each":
            shape, key, value, binders, source, condition = parts
            inner = {k: v for k, v in env.items() if k not in binders}
            plain = lambda node, label: None if node is None else self.plain(node, inner, label)
            return Expr(kind, (shape, plain(key, "A key"), plain(value, "An item of a new collection"), binders,
                               plain(source, "A collection"), plain(condition, "where"))), ()
        if kind in ("summarize", "history_count"):
            return node, ()  # binders range over plain list elements; quantities cannot enter lists
        return self._children(node, env, f"A value inside {kind}"), ()

    def _children(self, node, env, context):
        if isinstance(node, Expr):
            if node.kind in ("name", "literal"):
                return self.plain(node, env, context)
            if node.kind in ("list", "dict", "attr", "lookup"):
                return Expr(node.kind, tuple(self._children(p, env, context) for p in node.parts))
            return self.plain(node, env, context)
        if isinstance(node, tuple):
            return tuple(self._children(p, env, context) for p in node)
        return node


def _uses_units(statements) -> bool:
    def visit(node) -> bool:
        if isinstance(node, Expr):
            return node.kind in ("quantity", "convert") or any(visit(p) for p in node.parts)
        if isinstance(node, (tuple, list)):
            return any(visit(p) for p in node)
        return False

    for statement in statements:
        if statement.kind == "fn":
            params, result = statement.parts[1], statement.parts[2]
            if any(type_dimension(t) is not None for _, t in params) or type_dimension(result) is not None:
                return True
        if statement.kind == "foreign" and any(type_dimension(t) is not None
                                                for t in (*statement.parts[1], statement.parts[2])):
            return True
        if statement.kind == "let" and statement.parts[1] is not None and type_dimension(statement.parts[1]) is not None:
            return True
        if visit(statement.parts):
            return True
    return False


def check(statements: list[Stmt]) -> list[Stmt]:
    """Check dimensions and erase units. Programs without units are returned unchanged."""
    BORROWED.clear()
    if not _uses_units(statements):
        return statements
    signatures = {}
    for statement in statements:
        if statement.kind == "fn":
            name, params, result = statement.parts[:3]
            signatures[name] = ([type_dimension(t) for _, t in params], type_dimension(result))
    foreign = {}
    for statement in statements:
        if statement.kind == "foreign":
            path, params, result = statement.parts
            specs = []
            for t in (*params, result):
                if type_dimension(t) is not None and boundary_unit(t) is None:
                    raise BError("E_UNIT", f"{path} receives plain numbers; say which unit it uses, "
                                 f"for example {t[0]}[{_base_name(type_dimension(t))}]")
                specs.append(boundary_unit(t))
            if any(specs):
                foreign[path] = (specs[:-1], specs[-1])
    checker = _Checker(signatures, foreign)
    env: dict[str, Dim] = {}
    rewritten = []
    for statement in statements:
        kind, parts = statement.kind, statement.parts
        if kind == "fn":
            name, params, result, body, pure, requires, ensures = parts
            expected, result_dim = signatures[name]
            local = dict(env)
            for (n, _), d in zip(params, expected):  # a parameter shadows an outer binding
                if d:
                    local[n] = d
                else:
                    local.pop(n, None)
            new_body, dimension = checker.expr(body, local)
            if dimension != (result_dim or ()) and not (_is_zero(body) and result_dim):
                raise BError("E_UNIT", f"{name} returns {describe(dimension)}, "
                             f"but its declared result is {describe(result_dim or ())}")
            new_requires = checker.plain(requires, local, f"requires of {name}") if requires else None
            new_ensures = None
            if ensures is not None:
                new_ensures = checker.plain(ensures, {**local, "result": result_dim or ()}, f"ensures of {name}")
            new_params = [(n, FLOAT_SYNTAX if d is not None else t) for (n, t), d in zip(params, expected)]
            new_result = FLOAT_SYNTAX if result_dim is not None else result
            rewritten.append(Stmt(kind, (name, new_params, new_result, new_body, pure, new_requires, new_ensures)))
        elif kind == "let":
            name, annotation, value = parts
            new_value, dimension = checker.expr(value, env)
            declared = type_dimension(annotation) if annotation is not None else None
            if annotation is not None and dimension != (declared or ()):
                raise BError("E_UNIT", f"{name} is declared {describe(declared or ())}, "
                             f"but its value is {describe(dimension)}")
            env[name] = dimension
            value = checker.known(new_value, value)
            if value is not None and dimension:
                checker.bound[name] = value
            new_annotation = FLOAT_SYNTAX if declared is not None else annotation
            if annotation is None and dimension:
                new_annotation = None
            rewritten.append(Stmt(kind, (name, new_annotation, new_value)))
        elif kind == "foreign" and parts[0] in foreign:
            path, params, result = parts
            plain = [FLOAT_SYNTAX if type_dimension(t) is not None else t for t in params]
            new_result = FLOAT_SYNTAX if type_dimension(result) is not None else result
            rewritten.append(Stmt("foreign_units", (path, plain, new_result)))
        elif kind == "library_example":
            call, expected, tolerance, text = parts
            actual, dimension = checker.expr(call, env)
            wanted, expected_dimension = checker.expr(expected, env)
            if dimension != expected_dimension:
                raise BError("E_UNIT", f"{text}: the library returns {describe(dimension)}, "
                             f"the example states {describe(expected_dimension)}")
            margin = None
            if tolerance is not None:
                margin, margin_dimension = checker.expr(tolerance, env)
                if margin_dimension != dimension:
                    raise BError("E_UNIT", f"{text}: the tolerance is {describe(margin_dimension)}, "
                                 f"the result is {describe(dimension)}")
            rewritten.append(Stmt(kind, (actual, wanted, margin, text)))
        elif kind in ("print", "assert"):
            label = "print" if kind == "print" else "assert"
            rewritten.append(Stmt(kind, (checker.plain(parts[0], env, f"{label}"),)))
        else:
            rewritten.append(statement)
    return rewritten
