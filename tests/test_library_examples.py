import importlib
import json
import sys

import pytest

from b_lang.cli import main
from b_lang.compiler import compile_b
from b_lang.runtime import BExampleError
from b_lang.types import BError

AVIATION = ("use py:b_examples.aviation as aviation\n"
            "foreign aviation.fuel_burn(Duration[h]) -> Volume[gal]\n")


def run(source):
    exec(compile_b(source).code, {"__name__": "__b_test__"})


def test_a_fact_about_a_library_runs_before_the_rest_of_the_program(capsys):
    run(AVIATION + "example aviation.fuel_burn(2 h) == 19 gal within 0.001 gal\nprint 1\n")
    assert capsys.readouterr().out == "1\n"
    with pytest.raises(BExampleError, match="the library returned 19.0 gal"):
        run(AVIATION + "example aviation.fuel_burn(2 h) == 20 gal within 0.001 gal\nprint 1\n")
    assert capsys.readouterr().out == ""


def test_plain_examples_compare_exactly_and_are_listed_as_assumptions():
    checked = compile_b("use py:math as math\nexample math.floor(2.7) == 2\n")
    assert any("example math.floor(2.7) == 2: checked when the program reaches it" in a
               for a in checked.assumptions)
    run("use py:math as math\nexample math.hypot(3.0, 4.0) == 5.0\n")


@pytest.mark.parametrize(("line", "code", "fragment"), [
    ("example aviation.fuel_burn(2 h) == 19 kg", "E_UNIT", "Cannot express Volume in kg"),
    ("example aviation.fuel_burn(2 kg) == 19 gal", "E_UNIT", "must be Duration"),
    ("example aviation.fuel_burn(2 h) == 19 gal within 1 s", "E_UNIT", "Cannot express Duration in gal"),
    ("use py:b_examples.demo_lib as demo\nexample demo.clamp(5.0, 0.0, 3.0) == 3.0 was 2.0", "E_EXAMPLE",
     "state the new value"),
    ('example aviation.fuel_burn(2 h) == "many"', "E_UNIT", "returns Volume"),
])
def test_wrong_library_examples_are_rejected_before_running(line, code, fragment):
    with pytest.raises(BError) as exc:
        compile_b(AVIATION + line + "\n")
    assert exc.value.code == code and fragment in exc.value.message


def test_units_and_within_are_for_library_examples_only():
    with pytest.raises(BError, match="apply to examples of imported functions"):
        compile_b("fn fee(child: Bool) -> Int pure = 10\nexample fee(true) == 10 within 1\n")


def test_an_upgrade_that_changes_behavior_is_reported(tmp_path, monkeypatch, capsys):
    package = tmp_path / "tariff_lib"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "tariff.pyi").write_text("def vat(amount: float) -> float: ...\n")
    (package / "tariff.py").write_text("def vat(amount: float) -> float:\n    return amount * 0.25\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    program = tmp_path / "shop.bee"
    program.write_text("use py:tariff_lib.tariff as tariff\n"
                       "example tariff.vat(100.0) == 25.0\n"
                       "example tariff.vat(0.0) == 0.0\n")
    assert main(["check", str(program), "--library-examples"]) == 0
    assert "2 of 2 library example(s) hold" in capsys.readouterr().out

    # Version 2 of the library rounds to whole kronor and changes the rate.
    (package / "tariff.py").write_text("def vat(amount: float) -> float:\n    return float(round(amount * 0.12))\n")
    sys.modules.pop("tariff_lib.tariff", None)
    importlib.invalidate_caches()
    assert main(["check", str(program), "--library-examples", "--json"]) == 1
    rows = json.loads(capsys.readouterr().out)["library_examples"]
    assert [r["status"] for r in rows] == ["changed", "holds"]
    assert "the library returned 12.0" in rows[0]["message"]
    sys.modules.pop("tariff_lib.tariff", None)
    sys.modules.pop("tariff_lib", None)
