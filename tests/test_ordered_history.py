"""End-to-end checks for ordered counting, including the optimized execution plans."""
import importlib
import json

import pytest

from b_lang.cli import main
from b_lang.compiler import compile_b
from b_lang.lowering import PythonLowerer
from b_lang.types import BError


def executable(source, optimized):
    compiled = compile_b(source, strict=True)
    code = (compiled.code if optimized else
            compile(PythonLowerer().lower(compiled.ir), "<checked BIR>", "exec"))
    namespace = {}
    exec(code, namespace)
    return namespace


@pytest.mark.parametrize("optimized", [False, True])
def test_inequalities_agree_with_explicit_prior_positions(optimized):
    source = []
    cases = []
    operators = {"lt": ("<", int.__lt__), "le": ("<=", int.__le__),
                 "gt": (">", int.__gt__), "ge": (">=", int.__ge__)}
    for name, (symbol, predicate) in operators.items():
        for swapped in (False, True):
            fun = name + ("_swapped" if swapped else "")
            expr = f"q {symbol} p" if swapped else f"p {symbol} q"
            source.append(f"fn {fun}(xs: List[Int]) -> Int pure = count earlier p, q in xs where {expr}")
            cases.append((fun, predicate, swapped))
    namespace = executable("\n".join(source), optimized)
    for xs in ([], [1], [0, 0, 0], [5, 3, 1, 3, 7, -4], [2**175, -2**180, 2**175]):
        for fun, predicate, swapped in cases:
            expected = sum(any(predicate(q, p) if swapped else predicate(p, q) for p in xs[:i])
                           for i, q in enumerate(xs))
            assert namespace[fun](xs) == expected, (fun, xs)


@pytest.mark.parametrize("optimized", [False, True])
def test_specialized_and_generic_adjacency_and_previous_none(optimized):
    source = """
fn forward(xs: List[Int], limit: Int) -> Int pure =
    count adjacent p, q in xs where p > limit and q < limit
fn reversed(xs: List[Int], limit: Int) -> Int pure =
    count adjacent p, q in xs where q < limit and p > limit
fn pair(xs: List[Option[Int]]) -> Int pure = count adjacent p, q in xs where p == q
fn repeated(xs: List[Int]) -> Int pure = count earlier p, q in xs where p == q
fn target(xs: List[Int], k: Int) -> Int pure = count earlier p, q in xs where p*q == k
"""
    ns = executable(source, optimized)
    xs = [2, -1, -2, 0, 3, -4]
    assert ns["forward"](xs, 0) == ns["reversed"](xs, 0) == 2
    assert ns["pair"]([None, None, None, 0, 0, None, None]) == 4
    assert ns["repeated"]([4, 4, 4, 4]) == 3
    assert ns["target"]([3, 8, 3, 2, -5, 2], 6) == 2


def test_nested_captures_and_contextual_names():
    source = """
let earlier = 7
let adjacent = 8
fn count(a: Int, b: Int) -> Int pure = a + b
fn cuts(xs: List[Int], cutoffs: List[Int], offset: Int) -> Dict[Text,Int] pure =
    summarize limit in cutoffs {
        total: sum (count adjacent class, from in xs where class > limit + offset and from > limit + offset)
        seen: count
    }
let value = count(earlier, adjacent)
"""
    ns = executable(source, True)
    assert ns["value"] == 15
    assert ns["cuts"]([3, 4, 2, 3], [0, 1], 1) == {"total": 4, "seen": 2}


def test_dict_read_and_source_are_safe_to_reuse(tmp_path, monkeypatch):
    module = "b_history_rows"
    (tmp_path / (module + ".py")).write_text("""
calls = 0
def rows():
    global calls
    calls += 1
    return [{"s": 0, "e": 20}, {"s": 1, "e": 2}, {"s": 9, "e": 10}, {"s": 20}]
""")
    (tmp_path / (module + ".pyi")).write_text("def rows() -> list[dict[str, int]]: ...\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    source = f"""use py:{module} as recorder
fn overlaps(active: Bool) -> Int =
    if active then count earlier class, from in recorder.rows() where (from["s"] ?? 0) < (class["e"] ?? 0) else -1
"""
    ns = executable(source, True)
    recorder = importlib.import_module(module)
    assert ns["overlaps"](False) == -1
    assert recorder.calls == 0
    assert ns["overlaps"](True) == 2
    assert recorder.calls == 1


@pytest.mark.parametrize(("expression", "code"), [
    ("count earlier p, p in xs where true", "E_NAME"),
    ("count earlier p, xs in xs where true", "E_NAME"),
    ("count adjacent _b_tmp, q in xs where true", "E_NAME"),
    ("count adjacent p, q in [p] where true", "E_NAME"),
    ("count earlier p, q in 1 where true", "E_TYPE"),
    ("count earlier p, q in xs where p + q", "E_TYPE"),
    ("count adjacent p, q in xs where checked(p) == q", "E_HISTORY_PREDICATE"),
    ("count earlier p, q in xs where p % q == 0", "E_HISTORY_PREDICATE"),
    ("count earlier p, q in xs where p / q == 1.0", "E_HISTORY_PREDICATE"),
    ("count earlier p, q in loose where p == q", "E_HISTORY_PREDICATE"),
])
def test_binders_and_unsupported_history_predicates_are_rejected(expression, code):
    source = ("fn checked(n: Int) -> Int pure = n\n"
              f"fn work(xs: List[Int], loose: List[Any]) -> Int = {expression}")
    with pytest.raises(BError) as error:
        compile_b(source)
    assert error.value.code == code


def test_public_ir_reports_plan_and_run_counts_each_position_once(tmp_path, capsys):
    source = """fn overlap(xs: List[Int]) -> Int pure = count earlier p, q in xs where q <= p
print overlap([1, 0, -1, -2])"""
    path = tmp_path / "ordered.bee"
    path.write_text(source)
    for opts in ([], ["--optimized"]):
        assert main(["ir", str(path), *opts]) == 0
        program = json.loads(capsys.readouterr().out)
        node = program["statements"][0]["expression"]
        if node["op"] == "guard":
            node = node["operands"][0]
        assert node["op"] == "history_count" and node["type"] == "Int"
        assert node["value"]["plan"] == "prefix-max"
    assert main(["run", str(path), "--strict"]) == 0
    assert capsys.readouterr().out.strip() == "3"
