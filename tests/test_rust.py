"""Rust as a relative: signatures read with syn, calls across a JSON-lines border."""
import io
import shutil
from contextlib import redirect_stdout

import pytest

from b_lang.compiler import compile_b
from b_lang.runtime import ForeignError
from b_lang.types import BError

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="Rust toolchain not installed")

LIB = '''use std::collections::HashMap;

pub fn discounted(price: f64, percent: i64) -> f64 { price * (1.0 - percent as f64 / 100.0) }
pub fn total(prices: &[f64]) -> f64 { prices.iter().sum() }
pub fn shout(text: &str) -> String { text.to_uppercase() }
pub fn counts(words: Vec<String>) -> HashMap<String, i64> {
    let mut out = HashMap::new();
    for w in words { *out.entry(w).or_insert(0) += 1; }
    out
}
pub fn parse_qty(text: &str) -> Result<i64, String> { text.trim().parse::<i64>().map_err(|e| e.to_string()) }
pub fn first(xs: Vec<i64>) -> Option<i64> { xs.first().copied() }
pub struct Point { pub x: f64 }
pub fn origin() -> Point { Point { x: 0.0 } }
'''


@pytest.fixture(scope="module")
def crate(tmp_path_factory):
    root = tmp_path_factory.mktemp("rustprog")
    (root / "pricing" / "src").mkdir(parents=True)
    (root / "pricing" / "Cargo.toml").write_text('[package]\nname = "pricing"\nversion = "0.1.0"\nedition = "2021"\n')
    (root / "pricing" / "src" / "lib.rs").write_text(LIB)
    return root


@pytest.fixture
def program_dir(crate, monkeypatch):
    monkeypatch.setenv("B_PROGRAM_DIR", str(crate))


def run(source):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exec(compile_b(source, strict=True).code, {"__name__": "__b_test__"})
    return buffer.getvalue().splitlines()


def test_a_local_crate_is_typed_from_its_source(program_dir):
    assert run('use rust:"./pricing" as p\n'
               'print p.discounted(200.0, 15)\nprint p.total([1.5, 2.5])\nprint p.shout("hej")\n'
               'print to_json(p.counts(["a", "b", "a"]))\nprint p.first([]) ?? -1\n') == [
        "170.0", "4.0", "HEJ", '{"a": 2, "b": 1}', "-1"]


def test_an_err_becomes_none_when_declared(program_dir):
    assert run('use rust:"./pricing" as p\nforeign p.parse_qty(Text) -> Option[Int] on error\n'
               'print to_json([p.parse_qty(x) ?? 0 for x in ["3", "x"]])\n') == ["[3, 0]"]
    with pytest.raises(ForeignError):
        run('use rust:"./pricing" as p\nprint p.parse_qty("x")\n')


@pytest.mark.parametrize(("source", "fragment"), [
    ('use rust:"./pricing" as p\nlet x: Int = p.shout("a")\n', "expected Int, got Text"),
    ('use rust:"./pricing" as p\nprint p.origin()\n', "not a function B can type"),
    ('use rust:"serde" as s\n', "only local crates"),
])
def test_mistakes_at_the_rust_border_are_compile_errors(program_dir, source, fragment):
    with pytest.raises(BError) as exc:
        compile_b(source, strict=True)
    assert fragment in exc.value.message
