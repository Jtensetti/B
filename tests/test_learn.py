import shutil
from pathlib import Path

import pytest

from b_lang.ask import answer, ask
from b_lang.cli import main
from b_lang.compiler import compile_b
from b_lang.learn import learn, render
from b_lang.model import parse
from b_lang.types import BError

ROOT = Path(__file__).resolve().parents[1]
HEAD = "fn price(child: Bool, day: Text) -> Int pure by examples\n"
WEEK = 'domain day: "mon", "tue", "wed", "thu", "fri", "sat", "sun"\n'


def run(source):
    names = {}
    exec(compile_b(source, strict=True).code, names)
    return names


def codes(source):
    return [d.code for d in compile_b(source).diagnostics]


def test_syntax_keeps_old_identifiers():
    assert parse(HEAD)[0].parts == ("price", [("child", ("Bool", ())), ("day", ("Text", ()))], ("Int", ()), True)
    assert parse('example price(true, "sat") == 0')[0].parts == ("price", (True, "sat"), 0, None, False)
    assert parse("example g(-1) == -2 was 3")[0].parts == ("g", (-1,), -2, 3, True)
    assert parse('domain day: "mon", "tue"')[0].parts == ("day", ("mon", "tue"))
    assert parse("let example = 1\nlet was = example\nfn by(examples: Int) -> Int = examples")
    with pytest.raises(Exception):
        parse("example g(1) < 2")


def test_examples_define_a_function_that_runs_and_composes():
    source = (HEAD + 'example price(false, "mon") == 100\nexample price(true, "sat") == 0\n'
              'example price(false, "sat") == 100\nexample price(true, "mon") == 100\n'
              'fn total(child: Bool, day: Text) -> Int pure = price(child, day) + 10\n')
    names = run(source)
    assert [names["total"](c, d) for c, d in ((True, "sat"), (True, "mon"), (False, "sat"))] == [10, 110, 110]


def test_an_open_reading_is_a_warning_and_strict_rejects_it():
    source = HEAD + 'example price(false, "mon") == 100\nexample price(true, "sat") == 0\n'
    assert codes(source) == ["W_EXAMPLES_OPEN"]
    with pytest.raises(BError):
        compile_b(source, strict=True)


def test_examples_check_ordinary_functions_too():
    source = 'fn fee(child: Bool) -> Int pure = 10\nexample fee(true) == 10\n'
    assert run(source)["fee"](True) == 10
    with pytest.raises(BError) as exc:
        compile_b(source + "example fee(false) == 0\n")
    assert "program gives 10" in exc.value.message


def test_a_changed_result_must_state_its_old_value():
    base = 'fn fee(child: Bool) -> Int pure by examples\nexample fee(true) == 10\n'
    with pytest.raises(BError) as exc:
        compile_b(base + "example fee(true) == 12\n")
    assert "was 10" in exc.value.message
    with pytest.raises(BError) as exc:
        compile_b(base + "example fee(true) == 12 was 11\n")
    assert "current example says 10" in exc.value.message
    with pytest.raises(BError):
        compile_b(base + "example fee(false) == 12 was 11\n")
    assert run(base + "example fee(true) == 12 was 10\n")["fee"](False) == 12
    assert run(base + "example fee(true) == 10\n")["fee"](True) == 10


@pytest.mark.parametrize(("source", "fragment"), [
    (HEAD, "has none"),
    ('fn f(x: Float) -> Int pure by examples\nexample f(1.0) == 1\n', "Float"),
    ('fn f(x: Int) -> Int pure by examples\nexample f(true) == 1\n', "exact literal"),
    ('fn f(x: Int) -> Int pure by examples\nexample f(1) == "a"\n', "exact Int"),
    ('fn f(x: Int) -> Int pure by examples\nexample f(1, 2) == 1\n', "expects 1"),
    ('example g(1) == 1\n', "no function"),
    (WEEK + 'fn f(day: Text) -> Int pure = if day == "sön" then 1 else 0\n', "not in domain day"),
    (WEEK + HEAD + 'example price(true, "sön") == 0\n', "not in domain day"),
    ('domain day: "mon", 1\n', "one type"),
    ('domain day: "mon", "mon"\n', "repeats"),
])
def test_invalid_examples_and_domains(source, fragment):
    with pytest.raises(BError) as exc:
        compile_b(source)
    assert fragment in exc.value.message


def test_the_simplest_readings_are_found_and_the_human_question_asked():
    params = [("child", "Bool"), ("day", "Text")]
    first = learn("price", params, "Int", [((False, "mon"), 100), ((True, "sat"), 0)])
    assert render(first.rule, first.names) == "if child then 0 else 100"
    assert first.question_text() == 'price(false, "sat"): 100 or 0?'
    second = first.with_example((False, "sat"), 100)
    assert second.question_text() == 'price(true, "mon"): 0 or 100?'
    third = second.with_example((True, "mon"), 100)
    assert third.determined and render(third.rule, third.names) == 'if child and day == "sat" then 0 else 100'


def test_unseen_text_values_are_reported_without_a_domain():
    found = learn("price", [("day", "Text")], "Int", [(("mon",), 100), (("sat",), 0)])
    assert found.unseen_only and found.question_text().startswith("price(<another value>): ")
    assert sorted(found.answers) == [0, 100]
    closed = learn("price", [("day", "Text")], "Int", [(("mon",), 100), (("sat",), 0)], {},
                   {"day": ("mon", "tue", "sat")})
    assert closed.question == ("tue",) and not closed.unseen_only


def test_questions_find_an_integer_boundary_by_halving():
    rows = [((5,), 50), ((30,), 100)]
    asked = []
    while True:
        found = learn("price", [("age", "Int")], "Int", rows)
        if found.determined:
            break
        asked.append(found.question[0])
        rows.append((found.question, 50 if found.question[0] < 12 else 100))
    assert asked == [17, 11, 14, 12]
    assert render(found.rule, found.names) == "if age < 12 then 50 else 100"


def test_a_change_asks_about_its_neighbours_in_a_domain():
    params = [("child", "Bool"), ("day", "Text")]
    domains = {"day": ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    rows = [((False, "mon"), 100), ((True, "sat"), 0), ((False, "sat"), 100), ((True, "mon"), 100),
            ((True, "tue"), 100), ((True, "sun"), 0)]
    found = learn("price", params, "Int", rows, {}, domains)
    assert found.question == (False, "sun")
    found = found.with_example((False, "sun"), 100)
    assert found.question == (True, "wed")
    asked = []
    while not found.determined:
        asked.append(found.question)
        found = found.with_example(found.question, 0 if found.question[0] and found.question[1] in ("sat", "sun") else 100)
    assert asked == [(True, "wed"), (True, "fri")]
    assert all(found.rule.apply((c, d)) == (0 if c and d in ("sat", "sun") else 100)
               for c in (False, True) for d in domains["day"])


def test_a_value_only_one_example_supports_raises_a_neighbour_question():
    params = [("child", "Bool"), ("day", "Text")]
    domains = {"day": ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    rows = [((False, "mon"), 100), ((True, "sun"), 0), ((False, "sun"), 100), ((True, "mon"), 100),
            ((True, "tue"), 100)]
    found = learn("price", params, "Int", rows, {}, domains)
    assert render(found.rule, found.names) == 'if child and day == "sun" then 0 else 100'
    assert found.reason == "coverage" and found.question == (True, "sat") and found.answers == [100, 0]


def test_rules_the_search_cannot_express_are_refused():
    rows = "".join(f"example f({i}) == {i * i}\n" for i in range(8))
    with pytest.raises(BError) as exc:
        compile_b("fn f(x: Int) -> Int pure by examples\n" + rows)
    assert "write the function" in exc.value.message


def test_ask_answers_by_appending_one_example(tmp_path, capsys):
    path = tmp_path / "tickets.bee"
    shutil.copy(ROOT / "examples/learn/tickets.bee", path)
    assert main(["ask", str(path)]) == 2
    out = capsys.readouterr().out
    assert 'question: price(true, "tue"): 100 or 0?' in out
    assert 'then: if child and day == "sat" then 0 else 100' in out
    assert main(["ask", str(path), "--answer", "100", "--apply"]) == 0
    assert 'example price(true, "tue") == 100' in path.read_text()
    capsys.readouterr()
    assert main(["ask", str(path)]) == 2
    out = capsys.readouterr().out
    assert 'question: price(true, "fri"): 100 or 0?' in out and "why: only one example" in out
    for _ in range(2):  # Friday and Sunday, the neighbors of Saturday
        assert main(["ask", str(path), "--answer", "100", "--apply"]) == 0
    capsys.readouterr()
    assert main(["ask", str(path)]) == 0
    assert "settled" in capsys.readouterr().out
    assert main(["check", str(path), "--strict"]) == 0


def test_answer_rejects_values_that_were_not_offered():
    source = HEAD + 'example price(false, "mon") == 100\nexample price(true, "sat") == 0\n'
    with pytest.raises(BError):
        answer(ask(source), 50)
    assert 'example price(false, "sat") == 0' in answer(ask(source), 0)["file"]


def test_decision_experiment_b_side_is_reproducible():
    import importlib.util
    import json
    spec = importlib.util.spec_from_file_location("decisions", ROOT / "experiments/decisions/check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    recorded = {row["policy"]: row for row in json.loads(
        (ROOT / "experiments/decisions/results.json").read_text())["identification"]}
    for policy in module.POLICIES[:5]:
        seeds = [(x, policy["truth"](*x)) for x in (policy["inputs"][0], policy["inputs"][-1])]
        found, _, asked = module.ask_until_settled(policy, seeds)
        row = recorded[policy["name"]]
        assert (asked, module.accuracy(policy, found.rule)) == (row["questions"], row["b_accuracy"])
    assert recorded[module.POLICIES[5]["name"]]["b"].startswith("refused")
