"""v0.4: overloads and nullable/maps must never be silently assumed safe."""
import io
from contextlib import redirect_stdout

import pytest

from b_lang.compiler import compile_b
from b_lang.discovery import inspect_python
from b_lang.runtime import BBoundaryError, guard
from b_lang.types import BError, Overloads, parse_descriptor


def run(source: str):
    compiled = compile_b(source, strict=True)
    stream = io.StringIO()
    with redirect_stdout(stream):
        exec(compiled.code, {})
    return stream.getvalue(), compiled


def test_true_overloads_are_discovered():
    found = inspect_python('b_examples.poly_lib')
    binding = found.signatures['describe']
    assert isinstance(binding, Overloads)
    assert len(binding.options) == 2
    assert str(found.signatures['find_code'].result) == 'Option[Int]'
    assert str(found.signatures['adjust'].params[0]) == 'Dict[Text, Float]'


def test_overloads_choose_the_only_matching_declaration():
    out, checked = run('''use py:b_examples.poly_lib as m
let a: Int = m.describe(5) + 1
let b: Text = m.describe("hi") + "!"
print a
print b''')
    assert out.splitlines() == ['7', 'HI!']
    assert checked.assumptions


def test_wrong_overload_type_is_caught_before_running():
    with pytest.raises(BError) as e:
        compile_b('use py:b_examples.poly_lib as m\nprint m.describe(true)')
    assert e.value.code == 'E_TYPE'


def test_wrong_overload_arity_is_caught_before_running():
    with pytest.raises(BError) as e:
        compile_b('use py:b_examples.poly_lib as m\nprint m.describe()')
    assert e.value.code == 'E_ARITY'


def test_dynamic_overloads_dont_guess():
    with pytest.raises(BError) as e:
        compile_b('use py:b_examples.poly_lib as m\nuse py:json as json\nprint m.describe(json.loads("1"))')
    assert e.value.code == 'E_OVERLOAD_AMBIGUOUS'


def test_option_value_and_absence():
    out, _ = run('''use py:b_examples.poly_lib as m
let yes: Option[Int] = m.find_code("Ada")
let no: Option[Int] = m.find_code("missing")
print yes
print no''')
    assert out.splitlines() == ['42', 'None']


def test_optional_is_not_implicitly_nonnullable():
    with pytest.raises(BError) as e:
        compile_b('use py:b_examples.poly_lib as m\nlet x: Int = m.find_code("missing")')
    assert e.value.code == 'E_TYPE'


def test_optional_inferred_from_branches():
    out, _ = run('let x = if true then 4 else none\nlet y: Option[Int] = x\nprint y')
    assert out.strip() == '4'


def test_dict_literal_and_python_binding():
    out, _ = run('''use py:b_examples.poly_lib as m
let x: Dict[Text, Float] = m.adjust({"a": 1.0, "b": 2.0})
print x''')
    assert out.strip() == "{'a': 2.0, 'b': 4.0}"


def test_dict_wrong_key_rejected_preexecution():
    with pytest.raises(BError) as e:
        compile_b('let x = {2: "bad"}')
    assert e.value.code == 'E_TYPE'


def test_heterogeneous_dict_values_rejected_preexecution():
    with pytest.raises(BError) as e:
        compile_b('let x = {"a": 1, "b": "bad"}')
    assert e.value.code == 'E_TYPE'


def test_heterogeneous_list_values_rejected_preexecution():
    with pytest.raises(BError) as e:
        compile_b('let x = [1, "bad"]')
    assert e.value.code == 'E_TYPE'


def test_guard_catches_dishonest_nested_stub():
    checked = compile_b('use py:b_examples.poly_lib as m\nprint m.broken("x")', strict=True)
    with pytest.raises(BBoundaryError, match='Expected Int'):
        exec(checked.code, {})


@pytest.mark.parametrize('btype,value,expected', [
    ('Option[Int]', None, None),
    ('Option[Int]', 3, 3),
    ('Dict[Text, Int]', {"a": 4}, {"a": 4}),
    ('Dict[Text, Option[List[Float]]]', {"a": [2, 3.5], "b": None}, {"a": [2.0, 3.5], "b": None}),
    ('None', None, None),
])
def test_guards_roundtrip(btype, value, expected):
    assert guard(value, btype) == expected


def test_guard_snapshots_dicts_and_lists():
    source = {"x": [1]}
    copy = guard(source, 'Dict[Text, List[Int]]')
    source['x'][0] = 5
    assert copy == {"x": [1]}


@pytest.mark.parametrize('btype,value', [
    ('Option[Int]', 'bad'),
    ('None', 2),
    ('Dict[Text, Int]', {"a": True}),
    ('Dict[Text, Int]', {3: 3}),
    ('List[Option[Int]]', [4, 'bad']),
])
def test_guard_rejects_wrong_nested_values(btype, value):
    with pytest.raises(BBoundaryError):
        guard(value, btype)


def test_descriptor_parser_cannot_evaluate_text():
    with pytest.raises(BError, match='E_TYPE'):
        parse_descriptor('__import__("os").system("id")')


def test_polytypes_example_runs():
    from pathlib import Path
    out, compiled = run(Path('examples/polytypes.bee').read_text(encoding='utf-8'))
    assert out.splitlines()[:4] == ['B', '42', '42', 'None']
    assert compiled.diagnostics == []


def test_b_function_can_return_an_option():
    out, _ = run('fn keep(x: Option[Int]) -> Option[Int] = x\nprint keep(none)\nprint keep(3)')
    assert out.splitlines() == ['None', '3']


def test_option_truthiness_not_silently_accepted():
    with pytest.raises(BError) as err:
        compile_b('let value: Option[Int] = none\nprint if value then 2 else 1')
    assert err.value.code == 'E_TYPE'


def test_inspect_lists_each_overload_variant(capsys):
    import json
    from b_lang.cli import main
    assert main(['inspect', 'py:b_examples.poly_lib', '--json']) == 0
    doc = json.loads(capsys.readouterr().out)
    names = [item for item in doc['signatures'] if item['name'] == 'describe']
    assert [item['result'] for item in names] == ['Int', 'Text']
    assert [item['variant'] for item in names] == [1, 2]
    assert doc['behavior_proven'] is False


def test_union_optional_annotation_and_nested_dict_from_source(tmp_path, monkeypatch):
    from b_lang.discovery import inspect_python
    (tmp_path / 'b_union.py').write_text(
        'from typing import Union\n'
        'def choose(x: str) -> Union[None, dict[str, list[int]]]:\n'
        '    return None if x == "no" else {"ok": [1, 2]}\n', encoding='utf-8')
    monkeypatch.syspath_prepend(str(tmp_path))
    found = inspect_python('b_union')
    assert str(found.signatures['choose'].result) == 'Option[Dict[Text, List[Int]]]'
    result = compile_b('use py:b_union as m\nprint m.choose("yes")', strict=True)
    assert result.assumptions
