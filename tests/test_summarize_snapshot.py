import ast

from b_lang.compiler import compile_b


def test_field_mutation_preserves_initial_item_membership():
    program = compile_b("""fn collect(xs: List[Int], visit: Any) -> Dict[Text,Int] = summarize x in xs {
    n: count; net: sum visit(xs, x); first: min x default 0
}""")
    env = {}
    exec(program.code, env)
    seen = []

    def visit(xs, item):
        seen.append(item)
        if len(seen) == 1:
            xs[:] = [80, 90]
        return item

    assert env["collect"]([3, -2, 5], visit) == {"n": 3, "net": 6, "first": -2}
    assert seen == [3, -2, 5]


def test_unfiltered_count_needs_no_loop_and_ignores_user_len():
    program = compile_b("""fn len(xs: List[Int]) -> Int pure = 99
fn size(xs: List[Int]) -> Dict[Text,Int] pure = summarize x in xs { n: count; same: count }""", strict=True)
    env = {}
    exec(program.code, env)
    assert env["size"]([]) == {"n": 0, "same": 0}
    assert env["size"]([3, 0, -9]) == {"n": 3, "same": 3}
    helper, = (fn for fn in ast.parse(program.source).body
               if isinstance(fn, ast.FunctionDef) and fn.name.startswith("_b_summary_"))
    assert not any(isinstance(node, ast.For) for node in ast.walk(helper))
    assert sum(isinstance(node, ast.Call) for node in ast.walk(helper)) == 1
