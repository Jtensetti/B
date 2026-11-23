"""`foreign m.f(T) -> Option[R] on E`: a foreign call that can fail gives an Option."""
import io
import sys
from contextlib import redirect_stdout

import pytest

from b_lang.compiler import compile_b
from b_lang.types import BError

LIBRARY = '''
class NotServed(LookupError):
    pass

ZONES = {"SE": 1, "US": 4}

def zone(country: str) -> int:
    return ZONES[country.upper()]

def strict_zone(country: str) -> int:
    if country == "XX":
        raise NotServed(country)
    if country == "":
        raise ValueError("empty")
    return ZONES[country]
'''


@pytest.fixture
def library(tmp_path, monkeypatch):
    (tmp_path / "zones_lib.py").write_text(LIBRARY)
    monkeypatch.setattr(sys, "path", [str(tmp_path), *sys.path])
    sys.modules.pop("zones_lib", None)
    yield
    sys.modules.pop("zones_lib", None)


def run(source):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exec(compile_b(source, strict=True).code, {"__name__": "__b_test__"})
    return buffer.getvalue().splitlines()


def test_a_declared_exception_becomes_none(library):
    assert run('use py:zones_lib as z\n'
               'foreign z.zone(Text) -> Option[Int] on KeyError\n'
               'print to_json([z.zone(c) ?? 0 for c in ["SE", "us", "BR"]])\n'
               'print to_json([c for c in ["SE", "XX"] where z.zone(c) != none])\n') == ['[1, 4, 0]', '["SE"]']


def test_a_library_exception_matches_by_name_and_hierarchy(library):
    source = ('use py:zones_lib as z\n'
              'foreign z.strict_zone(Text) -> Option[Int] on {name}\n'
              'print to_json([z.strict_zone(c) ?? 0 for c in ["SE", "XX"]])\n')
    assert run(source.format(name="NotServed")) == ["[1, 0]"]
    assert run(source.format(name="LookupError")) == ["[1, 0]"]


def test_other_exceptions_still_propagate(library):
    with pytest.raises(ValueError):
        run('use py:zones_lib as z\n'
            'foreign z.strict_zone(Text) -> Option[Int] on NotServed, KeyError\n'
            'print z.strict_zone("") ?? 0\n')


@pytest.mark.parametrize(("declaration", "fragment"), [
    ("foreign z.zone(Text) -> Int on KeyError", "gives an Option"),
    ("foreign z.zone(Text) -> Option[Text] on KeyError", "restate it as that signature"),
    ("foreign z.zone(Int) -> Option[Int] on KeyError", "restate it as that signature"),
])
def test_the_declaration_only_restates_what_b_read(library, declaration, fragment):
    with pytest.raises(BError) as exc:
        compile_b(f"use py:zones_lib as z\n{declaration}\nprint z.zone(\"SE\") ?? 0\n", strict=True)
    assert fragment in exc.value.message


def test_the_result_must_be_handled_as_an_option(library):
    with pytest.raises(BError) as exc:
        compile_b('use py:zones_lib as z\nforeign z.zone(Text) -> Option[Int] on KeyError\n'
                  'let n: Int = z.zone("SE") + 1\n', strict=True)
    assert "Option" in exc.value.message
