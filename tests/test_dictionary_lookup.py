"""Dictionary lookup lets one B computation consume the output of another."""
import json
from pathlib import Path

import pytest

from b_lang.cli import main
from b_lang.compiler import compile_b
from b_lang.types import BError


def test_dynamic_key_and_nullable_value_use_one_option_layer():
    source = """
fn read(values: Dict[Text,Option[Int]], key: Text) -> Option[Int] pure = values[key]
fn fallback(values: Dict[Text,Option[Int]], key: Text) -> Int pure = read(values, key) ?? -7
"""
    namespace = {}
    exec(compile_b(source, strict=True).code, namespace)
    data = {"nil": None, "zero": 0, "negative": -3}
    assert [namespace["fallback"](data, key) for key in ("nil", "absent", "zero", "negative")] == [-7, -7, 0, -3]


def test_chained_lookup_of_dictionary_from_summary():
    source = """
fn measurements(xs: List[Int]) -> Dict[Text,Int] pure = summarize x in xs { n: count; net: sum x }
let reports = {"clock": measurements([2, -5])}
let clock = reports["clock"] ?? {"net": 100}
print clock["net"] ?? 0
"""
    namespace = {}
    compiled = compile_b(source, strict=True)
    exec(compiled.code, namespace)
    assert namespace["clock"] == {"n": 2, "net": -3}


@pytest.mark.parametrize("source", [
    'let report = {"n": 1}\nprint report[0]',
    'let xs = [1, 2]\nprint xs["n"]',
    'fn f(d: Dict[Text,Int]) -> Int pure = d["absent"]',
])
def test_invalid_key_container_and_unguarded_narrowing(source):
    with pytest.raises(BError) as error:
        compile_b(source, strict=True)
    assert error.value.code == "E_TYPE"


@pytest.mark.parametrize(("durations", "expected"), [
    ("[1000,480,550]", {"cues": 3, "short": 1, "missing_ms": 70}),
    ("[]", {"cues": 0, "short": 0, "missing_ms": 0}),
])
def test_subtitle_duration_program_reads_json_and_emits_named_results(durations, expected, monkeypatch, capsys):
    example = Path(__file__).resolve().parents[1] / "examples" / "cue-duration-audit.bee"
    monkeypatch.setattr("builtins.input", lambda: durations)
    assert main(["run", str(example), "--strict"]) == 0
    assert json.loads(capsys.readouterr().out) == expected
