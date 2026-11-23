import io
from contextlib import redirect_stdout
from fractions import Fraction

import pytest

from b_lang.compiler import compile_b
from b_lang.types import BError
from b_lang.units import CURRENCIES, UNITS


def output(source):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exec(compile_b(source, strict=True).code, {})
    return buffer.getvalue().split()


@pytest.mark.parametrize(("expression", "expected"), [
    ("5 km + 300 m as m", "5300.0"),
    ("1 mil as km", "10.0"),
    ("1 inch as mm", "25.4"),
    ("1 mi as km", "1.609344"),
    ("1 lb as g", "453.59237"),
    ("1 h + 30 min as min", "90.0"),
    ("1 kWh as MJ", "3.6"),
    ("1 GiB as MB", "1073.741824"),
    ("100 degC as degF", "212.0"),
    ("-40 degC as degF", "-40.0"),
    ("(20 degC + 5 dK) as degC", "25.0"),
    ("(25 degC - 20 degC) as dF", "9.0"),
    ("90 km per h as m per s", "25.0"),
    ("1 knot as km per h", "1.852"),
    ("3 dl + 2 cl as ml", "320.0"),
    ("2 hg as kg", "0.2"),
    ("1 atm as hPa", "1013.25"),
    ("50 öre + 2 kr as SEK", "2.5"),
    ("10 USD * (10.5 SEK per USD) as kr", "105.0"),
    ("1 inch == 2.54 cm", "True"),
    ("2 km > 1999 m", "True"),
])
def test_relations_that_never_change(expression, expected):
    assert output(f"print {expression}\n") == [expected]


def test_functions_take_and_return_quantities():
    source = ("fn speed(distance: Length, time: Duration) -> Speed pure = distance / time\n"
              "fn fare(d: Längd) -> Pengar[SEK] pure = d * (12 kr per mil)\n"
              "print speed(1 mil, 30 min) as km per h\n"
              "print fare(25 km) as kr\n")
    speed, fare = output(source)
    assert speed == "20.0"
    # Computed at runtime in Float: 25000 m * 0.0012 kr/m. Money is not yet exact decimal.
    assert float(fare) == pytest.approx(30.0) and fare != "30.0"
    names = {}
    exec(compile_b("fn speed(distance: Length, time: Duration) -> Speed pure = distance / time").code, names)
    assert names["speed"](1000.0, 100.0) == 10.0  # the units are erased: SI base values at runtime


@pytest.mark.parametrize(("source", "fragment"), [
    ("let x = 5 km + 2 kg", "Cannot add Length and Mass"),
    ("let x = 100 SEK + 5 USD", "Money[SEK] and Money[USD]"),
    ("let x = 100 kr as NOK", "Cannot express Money[SEK] in NOK"),
    ("let x = 20 degC + 5 degC", "two absolute temperatures"),
    ("let x = 2 * 20 degC", "cannot be multiplied"),
    ("print 5 km", "convert it with 'as'"),
    ("let x = 1 month", "no fixed length"),
    ("let x = 1 year", "Unknown unit 'year'"),
    ("let x = 1 inches", "Unknown unit 'inches'"),
    ("fn f(d: Length) -> Duration pure = d", "declared result is Duration"),
    ("fn f(d: Length) -> Length pure = d\nlet x = f(3 kg)", "Argument 1 of f must be Length"),
    ("let x: Mass = 3 m", "declared Mass"),
    ("let x = 3 km > 2 s", "Cannot compare"),
    ("let x = if true then 1 km else 1 h", "choose between"),
    ("let xs = [1 km]", "plain number"),
    ("fn f(x: List[Length]) -> Int pure = 1", "inside List"),
    ("fn f(p: Money[XYZ]) -> Int pure = 1", "currency code"),
    ("let x = 1 degC per s", "absolute temperature"),
])
def test_dimension_errors(source, fragment):
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert exc.value.code == "E_UNIT" and fragment in exc.value.message


def test_zero_needs_no_unit_and_plain_programs_are_untouched():
    assert output("fn f(d: Length) -> Bool pure = d > 0\nprint f(1 m)\n") == ["True"]
    plain = "let x = 7 / 2\nprint x\n"
    assert output(plain) == ["3.5"]


def test_unit_table_is_consistent():
    assert UNITS["kr"][1] == UNITS["SEK"][1] and UNITS["NOK"][1] != UNITS["SEK"][1]
    assert all(code in UNITS for code in CURRENCIES)
    assert UNITS["inch"][0] == Fraction(254, 10000) and UNITS["day"][0] == 86400
    assert "month" not in UNITS and "year" not in UNITS


def test_records_lists_and_containment_work_in_a_program_with_units():
    source = ('record Parcel { id: Text, kg: Float }\n'
              'fn mass(p: Parcel) -> Mass = p.kg * 1 kg\n'
              'let parcels = [{id = "a", kg = 2.0}, {id = "b", kg = 0.5}]\n'
              'print {p.id: mass(p) as lb for p in parcels where "a" in [p.id]}\n'
              'print 1 inch3 as cm3\n')
    assert output(source)[0].startswith("{'a': 4.40924")
    assert output(source)[1] == "16.387064"
