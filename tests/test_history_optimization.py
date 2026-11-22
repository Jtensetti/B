import pytest

from b_lang.compiler import compile_b


@pytest.mark.parametrize(("mode", "predicate", "before", "after", "expected"), [
    ("adjacent", "(if true then false else old > 0) and (if true then true else now > 0)",
     "previous-test", "previous-item", 0),
    ("earlier", "(if true then 0 else old) < (if true then 1 else now)",
     "prefix-min", "prefix-search", 3),
    ("earlier", "if true then old > now else old == now",
     "prefix-search", "prefix-max", 2),
])
def test_optimizer_replans_the_predicate_after_folding(mode, predicate, before, after, expected):
    c = compile_b(f"fn tally(xs: List[Int]) -> Int pure = count {mode} old, now in xs where {predicate}",
                  strict=True)
    def expression(ir):
        node = ir.statements[0].expr
        return node.operands[0] if node.op == "guard" else node
    assert expression(c.ir).data["plan"] == before
    optimized = expression(c.optimized_ir)
    assert optimized.data["plan"] == after
    if after in {"prefix-search", "previous-item"}:
        assert "past_side" not in optimized.data
    env = {}
    exec(c.code, env)
    assert env["tally"]([1, 4, 3, 0]) == expected
