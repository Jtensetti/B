"""Tests for B 0.19 sibling-language features:
- 5-ecosystem interop (Python, .NET, Node.js, Go, Rust)
- Units & currencies (E_UNIT / E_CURRENCY)
- Typed records, local let-in, pipelines, list comprehensions, pure built-ins
- False-friend static checks & behavioral dependency locking (b lock / b check --lock)
- Independent JavaScript BIR backend differential equivalence
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from b_lang.cli import main
from b_lang.compiler import compile_b
from b_lang.lock import create_lock, verify_lock
from b_lang.lowering_js import JavaScriptLowerer
from b_lang.types import BError


def run_b(source: str, *, strict: bool = True, file_path: Path | None = None) -> str:
    compiled = compile_b(source, strict=strict)
    out = io.StringIO()
    ns = {"__name__": "__b_test__"}
    if file_path is not None:
        ns["__file__"] = str(file_path.resolve())
    try:
        with redirect_stdout(out):
            exec(compiled.code, ns, ns)
    finally:
        if "_b_js_session" in ns:
            ns["_b_js_session"].close()
    return out.getvalue()


@pytest.mark.skipif(
    any(shutil.which(t) is None for t in ("dotnet", "node", "go", "cargo")),
    reason="Requires dotnet, node, go, and cargo",
)
def test_five_ecosystem_composition():
    source = '''use py:statistics as stats
use net:System.Math as NetMath
use js:"node:path/posix" as jspath
use go:strings as gstr
use rs:std.f64 as rf

let avg: Float = stats.mean([2.0, 4.0, 6.0])
let root: Float = NetMath.Sqrt(avg * 4.0)
let clean: Text = jspath.normalize("/releases/v1/../v2/app.tar.gz")
let upper: Text = gstr.ToUpper(jspath.basename(clean))
let rounded: Float = rf.round(2.5)
print upper
print root
print rounded
'''
    out = run_b(source)
    lines = out.strip().splitlines()
    assert lines[0] == "APP.TAR.GZ"
    assert abs(float(lines[1]) - 4.0) < 1e-9
    assert abs(float(lines[2]) - 3.0) < 1e-9


def test_units_and_currencies_compile_and_reject_mismatches():
    good = '''unit m, s
unit km = 1000 m
currency SEK, EUR

fn total_m(a: Float[km], b: Float[m]) -> Float[m] pure = (a to m) + b
fn eur_to_sek(amount: Float[EUR], rate: Float) -> Float[SEK] pure = (scalar(amount) * rate) as SEK

let d: Float[m] = total_m(1.5 as km, 250.0 as m)
let p: Float[SEK] = eur_to_sek(10.0 as EUR, 11.5)
print scalar(d)
print scalar(p)
'''
    lines = run_b(good).strip().splitlines()
    assert abs(float(lines[0]) - 1750.0) < 1e-9
    assert abs(float(lines[1]) - 115.0) < 1e-9

    # Wrong unit addition -> E_UNIT
    with pytest.raises(BError) as err:
        compile_b("unit m, s\nlet bad = (1.0 as m) + (2.0 as s)\n")
    assert err.value.code == "E_UNIT"

    # Wrong unit conversion -> E_UNIT
    with pytest.raises(BError) as err:
        compile_b("unit m, s\nlet bad = (1.0 as m) to s\n")
    assert err.value.code == "E_UNIT"

    # Re-tagging unit -> E_UNIT
    with pytest.raises(BError) as err:
        compile_b("unit m, km\nlet bad = (1.0 as m) as km\n")
    assert err.value.code == "E_UNIT"

    # Mixing currencies -> E_CURRENCY
    with pytest.raises(BError) as err:
        compile_b("currency SEK, EUR\nlet bad = (10.0 as SEK) + (5.0 as EUR)\n")
    assert err.value.code == "E_CURRENCY"

    # Implicit currency conversion -> E_CURRENCY
    with pytest.raises(BError) as err:
        compile_b("currency SEK, EUR\nlet bad = (10.0 as SEK) to EUR\n")
    assert err.value.code == "E_CURRENCY"

    # Passing bare Float where Float[EUR] is expected -> E_CURRENCY
    with pytest.raises(BError) as err:
        compile_b("currency EUR\nfn charge(x: Float[EUR]) -> Float[EUR] pure = x\nlet z = charge(10.0)\n")
    assert err.value.code == "E_CURRENCY"


def test_records_let_in_pipelines_and_comprehensions():
    source = '''unit m
unit km = 1000 m
currency EUR

record Leg {
    id: Text
    dist: Float[km]
    fee: Float[EUR]
}

fn adjust(leg: Leg) -> Leg pure =
    let meters = leg.dist to m in
    if meters > 5000.0 as m then leg with { fee: leg.fee * 1.1 } else leg

let legs = [Leg("a", 2.0 as km, 10.0 as EUR), Leg("b", 10.0 as km, 20.0 as EUR)]
let updated = [adjust(x) for x in legs]
let fees = [scalar(x.fee) for x in updated where scalar(x.fee) > 15.0]
let norm = "  hello  " |> str_trim |> str_upper
print json_encode(fees)
print norm
'''
    lines = run_b(source).strip().splitlines()
    assert json.loads(lines[0]) == [pytest.approx(22.0)]
    assert lines[1] == "HELLO"


def test_false_friend_static_checks():
    # Rounding mismatch: Go math.Round is half_away_zero, not half_even
    with pytest.raises(BError) as err:
        compile_b("use go:math as gmath\nexpect gmath.Round rounding = half_even\n")
    assert err.value.code == "E_FALSE_FRIEND"

    # String unit mismatch: Rust len_bytes is utf8_bytes, not codepoints
    with pytest.raises(BError) as err:
        compile_b("use rs:std.str as rstr\nexpect rstr.len_bytes string_unit = codepoints\n")
    assert err.value.code == "E_FALSE_FRIEND"

    # JS 53-bit safe integer overflow caught statically
    with pytest.raises(BError) as err:
        compile_b('use js:"@fixture/num" as n\nforeign n.id(Int) -> Int\nlet x = n.id(9007199254740993)\n')
    assert err.value.code == "E_FALSE_FRIEND"

    # Matching expectation passes!
    compile_b("use go:math as gmath\nexpect gmath.RoundToEven rounding = half_even\n", strict=True)


def test_behavioral_dependency_lock_catches_signature_and_silent_drift(tmp_path, monkeypatch):
    pkg = tmp_path / "mylib.py"
    pkg.write_text("def price(x: float) -> float:\n    return round(x)\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    src = tmp_path / "app.bee"
    src.write_text(
        "use py:mylib as lib\n"
        "probe lib.price(2.5) == 2.0\n"
        "let out: Float = lib.price(2.5)\n"
        "print out\n",
        encoding="utf-8",
    )
    lock_data = create_lock(src.read_text(), source_file=src)
    report = verify_lock(src.read_text(), lock_data, source_file=src, strict=True)
    assert report["status"] == "verified"
    assert report["probes_checked"] == 1

    # 1. Silently change library behavior while keeping exact same type signature!
    pkg.write_text("import math\ndef price(x: float) -> float:\n    return float(math.floor(x + 0.5))\n", encoding="utf-8")
    sys.modules.pop("mylib", None)
    with pytest.raises(BError) as err:
        verify_lock(src.read_text(), lock_data, source_file=src, strict=True)
    assert err.value.code == "E_BEHAVIOR_DRIFT"

    # 2. Change library signature (extra required parameter)!
    pkg.write_text("def price(x: float, currency: str) -> float:\n    return round(x)\n", encoding="utf-8")
    sys.modules.pop("mylib", None)
    with pytest.raises(BError) as err:
        verify_lock(src.read_text(), lock_data, source_file=src, strict=True)
    assert err.value.code in ("E_ARITY", "E_LOCK_SIGNATURE")

    # 3. Unannotated Python signature drift caught by lockfile AST verification!
    pkg.write_text("def price(x, currency):\n    return round(x)\n", encoding="utf-8")
    sys.modules.pop("mylib", None)
    src_foreign = tmp_path / "app_f.bee"
    src_foreign.write_text(
        "use py:mylib as lib\n"
        "foreign lib.price(Float) -> Float\n"
        "let out: Float = lib.price(2.5)\n"
        "print out\n",
        encoding="utf-8",
    )
    with pytest.raises(BError) as err:
        verify_lock(src_foreign.read_text(), lock_data, source_file=src_foreign, strict=True)
    assert err.value.code == "E_LOCK_SIGNATURE"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js unavailable")
def test_second_independent_js_backend_matches_python_backend(tmp_path):
    source = '''unit m
unit km = 1000 m
record Sample { label: Text; dist: Float[km]; ticks: Int }

fn classify(n: Int) -> Text pure = cases n {
    < 0 => "neg"
    == 0 => "zero"
    <= 5 => "small"
    else => "large"
}

fn late_pairs(xs: List[Int]) -> Int pure =
    count adjacent a, b in xs where a > 0 and b > 0

fn report(xs: List[Int]) -> Dict[Text, Int] pure = summarize x in xs {
    n: count
    pos: count where x > 0
    total: sum x where x > 0
    hi: max x default 0
}

let s = Sample("run", 2.5 as km, 4)
let meters: Float[m] = s.dist to m
let doubled = [x * 2 for x in [1, 2, 3, 4] where x > 1]
print classify(-3)
print classify(0)
print classify(4)
print classify(9)
print late_pairs([1, 2, 0, 3, 4, 5])
print json_encode(report([-2, 3, 5, 1]))
print json_encode(doubled)
print round_even(2.5)
print round_away(2.5)
print rem_euclid(-5, 4)
print rem_trunc(-5, 4)
print scalar(meters)
'''
    py_out = run_b(source)
    compiled = compile_b(source, strict=True)
    js_code = JavaScriptLowerer().lower(compiled.optimized_ir)
    js_file = tmp_path / "prog.cjs"
    js_file.write_text(js_code, encoding="utf-8")
    proc = subprocess.run(["node", str(js_file)], capture_output=True, text=True, check=True)
    # Normalize float formatting (2500.0 vs 2500) on the last line
    py_lines = py_out.strip().splitlines()
    js_lines = proc.stdout.strip().splitlines()
    assert py_lines[:-1] == js_lines[:-1]
    assert abs(float(py_lines[-1]) - float(js_lines[-1])) < 1e-9


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js unavailable")
def test_b_020_structural_records_heterogeneous_summarize_and_dimensioned_keeping(tmp_path):
    source = '''unit m
unit km = 1000 m
currency EUR

record Leg {
    id: Text
    dist: Float[km]
    fee: Float[EUR]
    valid: Bool
}

fn fee_rule(dist: Float[km]) -> Float[EUR] pure =
    (5.0 + 0.5 * scalar(dist)) as EUR

fn is_vip(id: Text) -> Bool pure = false
also is_vip("sto-01") keeping fee_rule

fn eval_leg(leg: Leg) =
    let vip = is_vip(leg.id) in
    let base =
        if vip
        then 0.0 as EUR
        else fee_rule(leg.dist) in
    record {
        valid: leg.valid,
        vip,
        dist: leg.dist,
        fee: base,
        cents: round_even(scalar(base) * 100.0),
    }

let legs = [
    Leg(id: "sto-01", dist: 10.0 as km, fee: 0.0 as EUR, valid: true),
    Leg(dist: 20.0 as km, id: "got-02", valid: true, fee: 0.0 as EUR),
    Leg(id: "bad", dist: 99.0 as km, fee: 0.0 as EUR, valid: false),
]
let evaluated = [eval_leg(l) for l in legs]
let s = summarize item in evaluated {
    total: count
    valid: count where item.valid
    total_km: sum item.dist where item.valid
    total_eur: sum item.fee where item.valid
    max_cents: max item.cents where item.valid default 0
}
let total_m = round_even(scalar(s.total_km to m))
let out = record {
    total: s.total,
    valid: s.valid,
    total_m,
    total_eur_cents: round_even(scalar(s.total_eur) * 100.0),
    max_cents: s.max_cents,
}
print json_encode(out)
'''
    py_out = run_b(source).strip()
    assert json.loads(py_out) == {
        "total": 3,
        "valid": 2,
        "total_m": 30000,
        "total_eur_cents": 1500,
        "max_cents": 1500,
    }
    compiled = compile_b(source, strict=True)
    js_code = JavaScriptLowerer().lower(compiled.optimized_ir)
    js_file = tmp_path / "b020.cjs"
    js_file.write_text(js_code, encoding="utf-8")
    proc = subprocess.run(["node", str(js_file)], capture_output=True, text=True, check=True)
    assert json.loads(proc.stdout.strip()) == json.loads(py_out)

    # Verify static safety on heterogeneous summarize: mixing km + EUR is caught!
    bad = '''unit km
currency EUR
record Item { d: Float[km]; p: Float[EUR] }
let s = summarize x in [Item(1.0 as km, 2.0 as EUR)] {
    dk: sum x.d
    pe: sum x.p
}
print s.dk + s.pe
'''
    with pytest.raises(BError) as err:
        compile_b(bad, strict=True)
    assert err.value.code == "E_CURRENCY"

    # Verify structural records in count adjacent and multiline parenthesized expressions
    hist_src = '''let items = [
    record { ok: false, n: 1 },
    record { ok: false, n: 2 },
    record { ok: true, n: 3 },
]
fn both(a: Bool, b: Bool) -> Bool pure = (
    a
    and b
)
let adj = count adjacent p, c in items where not p.ok and not c.ok
print adj
print both(true, true)
'''
    assert run_b(hist_src).strip().splitlines() == ["1", "True"]


