"""Find the smallest joint observation that separates two finite specifications."""
import json
from itertools import combinations, product

from b_lang.clarification import compare
from b_lang.compiler import compile_b
from b_lang.edit_clarification import decide_edit


RANKS = (0, 1, 2)
BASE = "fn gap(rank: Int) -> Int pure requires rank >= 0 and rank <= 2 = rank + 1"
MIXED = BASE.replace("= rank + 1", "= if rank == 0 then rank + 1 else rank + 2")
# Both expressions describe exactly the observable one-row permissions in both worlds.
POINTWISE = {"one_style": "result == rank + 1 or result == rank + 2",
             "independent_rows": "result >= rank + 1 and result <= rank + 2"}


def minimum_joint_question(left, right):
    """Search all projections, starting with one rank. Catalogs contain complete layouts."""
    levels = []
    for count in range(1, len(RANKS) + 1):
        separators = []
        for indices in combinations(RANKS, count):
            def projections(layouts):
                return {tuple(layout[i] for i in indices) for layout in layouts}
            a, b = projections(left), projections(right)
            for values in sorted(a ^ b):
                separators.append({"ranks": list(indices), "gaps": list(values),
                                   "left_allows": values in a, "right_allows": values in b})
        levels.append(len(separators))
        if separators:
            return {"arity": count, "separating_patterns_by_arity": levels, "question": separators[0]}
    return {"arity": None, "separating_patterns_by_arity": levels, "question": None}


def measure():
    bits = tuple(product((0, 1), repeat=len(RANKS)))

    def layout(style):
        return tuple(rank + 1 + style[rank] for rank in RANKS)

    independent = {layout(style) for style in bits}
    uniform = {layout(style) for style in bits if len(set(style)) == 1}
    even = {layout(style) for style in bits if sum(style) % 2 == 0}
    mixed = (1, 3, 4)
    program, revised = compile_b(BASE).ir, compile_b(MIXED).ir
    args = ("gap", POINTWISE, {"rank": list(RANKS)}, [1, 2, 3, 4])
    current = compare(program, *args)
    edit = decide_edit(program, revised, *args)
    return {
        "layouts": {"independent": len(independent), "one_style": len(uniform), "even": len(even)},
        "complete_input_grid": list(RANKS), "pointwise_comparison": current["status"],
        "mixed_layout": mixed, "pointwise_edit_decision": edit["status"],
        "mixed_allowed_with_one_style": mixed in uniform,
        "mixed_allowed_with_independent_rows": mixed in independent,
        "one_style_vs_independent": minimum_joint_question(uniform, independent),
        "even_vs_independent": minimum_joint_question(even, independent),
    }


if __name__ == "__main__":
    print(json.dumps(measure(), indent=2))
