import io
from contextlib import redirect_stdout
from fractions import Fraction

import pytest

import b_lang.units as units
from b_lang.compiler import compile_b
from b_lang.types import BError

AVIATION = ("use py:b_examples.aviation as aviation\n"
            "foreign aviation.takeoff_distance(Speed[knot], Mass[lb]) -> Length[ft]\n"
            "foreign aviation.fuel_burn(Duration[h]) -> Volume[gal]\n")


def output(source):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exec(compile_b(source).code, {})
    return [float(x) for x in buffer.getvalue().split()]


def test_a_python_library_in_feet_and_pounds_receives_si_values_converted():
    roll, fuel, margin = output(
        AVIATION
        + "fn margin(available: Length, speed: Speed, weight: Mass) -> Length =\n"
          "    available - aviation.takeoff_distance(speed, weight)\n"
          "print aviation.takeoff_distance(222.24 km per h, 2400 lb) as m\n"
          "print aviation.fuel_burn(90 min) as l\n"
          "print margin(800 m, 120 knot, 2400 lb) as m\n")
    # 120 knots and 2400 lb in the library's own units: 38.4 ft, i.e. 11.70432 m.
    assert roll == pytest.approx(0.0004 * 2400 * 2 ** 2 * 10 * 0.3048)
    assert fuel == pytest.approx(9.5 * 1.5 * 3.785411784)
    assert margin == pytest.approx(800 - roll)


@pytest.mark.parametrize(("extra", "fragment"), [
    ("print aviation.takeoff_distance(1088 kg, 120 knot) as m\n", "Argument 1 of aviation.takeoff_distance must be Speed, got Mass"),
    ("print aviation.fuel_burn(2.0) as l\n", "must be Duration, got a plain number"),
    ("print aviation.fuel_burn(1 h)\n", "convert it with 'as'"),
])
def test_wrong_units_at_the_border_fail_before_running(extra, fragment):
    with pytest.raises(BError) as exc:
        compile_b(AVIATION + extra)
    assert exc.value.code == "E_UNIT" and fragment in exc.value.message


@pytest.mark.parametrize(("declaration", "code", "fragment"), [
    ("foreign aviation.fuel_burn(Duration) -> Volume[gal]", "E_UNIT", "say which unit it uses, for example Duration[s]"),
    ("foreign aviation.fuel_burn(Duration[kg]) -> Volume[gal]", "E_UNIT", "measures Mass, not Duration"),
    ("foreign aviation.fuel_burn(Duration[h]) -> Text", "E_FOREIGN", "different signature"),
    ("foreign aviation.fuel_burn(Float) -> Float", "E_FOREIGN", "already exists"),
])
def test_a_unit_declaration_can_only_restate_the_relatives_signature(declaration, code, fragment):
    with pytest.raises(BError) as exc:
        compile_b("use py:b_examples.aviation as aviation\n" + declaration + "\n")
    assert exc.value.code == code and fragment in exc.value.message


def test_registered_dotnet_methods_can_carry_units():
    checked = compile_b("use net:System.Math as math\nforeign math.Sqrt(Area[m2]) -> Length[m]\n"
                        "fn side(a: Area) -> Length = math.Sqrt(a)\n")
    assert checked.ir
    with pytest.raises(BError):
        compile_b("use net:System.Math as math\nforeign math.Sqrt(Area[m2]) -> Length[m]\n"
                  "let x = math.Sqrt(4 m) as m\n")


class _Quantity:
    TABLE = {"furlong": (Fraction(201168, 1000), {"[length]": 1}),
             "stone": (Fraction(635029318, 10**8), {"[mass]": 1}),
             "mil": (Fraction(254, 10**7), {"[length]": 1}),  # pint's mil is a thousandth of an inch
             "lumen": (1, {"[luminosity]": 1, "[strange]": 1})}

    def __init__(self, magnitude, name):
        if name not in self.TABLE:
            raise KeyError(name)
        factor, self.dimensionality = self.TABLE[name]
        self.magnitude = float(factor) * magnitude

    def to_base_units(self):
        return self


class _Registry:
    Quantity = _Quantity


@pytest.fixture
def stand_in_pint():
    units.use_vocabulary(_Registry(), "pint (test stand-in)")
    yield
    units._vocabulary = None


def test_missing_units_are_borrowed_and_reported(stand_in_pint):
    checked = compile_b("print 1 furlong as m\nprint 2 stone as kg\nprint 1 mil as km\n")
    assert "unit furlong from pint (test stand-in): definition borrowed, not checked by B" in checked.assumptions
    assert not any("mil" in a for a in checked.assumptions)  # B's own word wins: a Swedish mil
    assert output("print 1 furlong as m\nprint 1 mil as km\n") == [201.168, 10.0]
    with pytest.raises(BError, match="Unknown unit 'lumen'"):
        compile_b("print 1 lumen as cd\n")  # a dimension B cannot map is not borrowed
    with pytest.raises(BError, match="Unknown unit 'smoot'"):
        compile_b("print 1 smoot as m\n")


def test_without_a_vocabulary_only_bs_own_units_exist():
    units.use_vocabulary(None)
    try:
        with pytest.raises(BError, match="Unknown unit 'furlong'"):
            compile_b("print 1 furlong as m\n")
    finally:
        units._vocabulary = None


def test_a_library_result_plus_a_known_quantity_keeps_both_terms():
    # Regression: exact folding once looked values up by id(), which Python reuses.
    source = AVIATION + "".join(f"let f{i} = aviation.fuel_burn({i + 1} h) + 12 l\n" for i in range(40))
    source += "print f39 as l\n"
    assert output(source) == [pytest.approx(9.5 * 40 * 3.785411784 + 12)]


def test_unit_mistake_study_is_current():
    import json
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run([sys.executable, "experiments/border-units/check.py"], capture_output=True,
                         text=True, cwd=root, check=True)
    assert json.loads(run.stdout) == json.loads((root / "experiments/border-units/results.json").read_text())
