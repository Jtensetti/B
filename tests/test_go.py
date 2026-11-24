"""Go as a relative: signatures read with go/types, calls across a JSON-lines border."""
import io
import shutil
from contextlib import redirect_stdout

import pytest

from b_lang.compiler import compile_b
from b_lang.runtime import ForeignError
from b_lang.types import BError

pytestmark = pytest.mark.skipif(shutil.which("go") is None, reason="Go toolchain not installed")

GEO = '''package geo

import "errors"

func Scale(xs []float64, k float64) []float64 {
	out := make([]float64, len(xs))
	for i, x := range xs {
		out[i] = x * k
	}
	return out
}

func Zone(prefix string) (int, error) {
	if prefix == "1" {
		return 1, nil
	}
	return 0, errors.New("no zone for " + prefix)
}

func Count(words map[string]int) int {
	n := 0
	for _, v := range words {
		n += v
	}
	return n
}

type Point struct{ X float64 }

func Origin() Point { return Point{} }
'''


@pytest.fixture
def geo(tmp_path, monkeypatch):
    folder = tmp_path / "geo"
    folder.mkdir()
    (folder / "go.mod").write_text("module example.com/geo\n\ngo 1.22\n")
    (folder / "geo.go").write_text(GEO)
    monkeypatch.setenv("B_PROGRAM_DIR", str(tmp_path))


def run(source):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exec(compile_b(source, strict=True).code, {"__name__": "__b_test__"})
    return buffer.getvalue().splitlines()


def test_the_standard_library_is_typed_from_go_metadata():
    assert run('use go:"strings" as s\nprint s.Repeat("ab", 3)\nprint to_json(s.Split("a,b", ","))\n'
               'let n: Int = s.Count("cheese", "e")\nprint n\n') == ["ababab", '["a", "b"]', "3"]


def test_a_local_module_with_lists_maps_and_units(geo):
    assert run('use go:"./geo" as geo\n'
               'print to_json(geo.Scale([1.0, 2.5], 2.0))\n'
               'print geo.Count({"a": 2, "b": 3})\n') == ["[2.0, 5.0]", "5"]


def test_a_go_error_becomes_none_when_declared(geo):
    assert run('use go:"./geo" as geo\nforeign geo.Zone(Text) -> Option[Int] on error\n'
               'print to_json([geo.Zone(p) ?? 0 for p in ["1", "7"]])\n') == ["[1, 0]"]
    with pytest.raises(ForeignError):
        run('use go:"./geo" as geo\nprint geo.Zone("7")\n')


@pytest.mark.parametrize(("source", "fragment"), [
    ('use go:"strings" as s\nlet x: Int = s.Repeat("a", 2)\n', "expected Int, got Text"),
    ('use go:"strings" as s\nprint s.Repeat(2, "a")\n', "argument 1"),
    ('use go:"./geo" as geo\nprint geo.Origin()\n', "not a function B can type"),
    ('use go:"./geo" as geo\nforeign geo.Zone(Text) -> Option[Int] on KeyError\n', "is caught as 'on error'"),
])
def test_mistakes_at_the_go_border_are_compile_errors(geo, source, fragment):
    with pytest.raises(BError) as exc:
        compile_b(source, strict=True)
    assert fragment in exc.value.message
