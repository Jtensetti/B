import json
from pathlib import Path

from b_lang.compiler import compile_b
from b_lang.joint import check_joint
from b_lang.register_view import function_view


EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "registers"


def test_shift_invariance_depends_on_the_coordinate_convention():
    source = (EXAMPLES / "displacement.bee").read_text()
    request = json.loads((EXAMPLES / "shifts.json").read_text())
    program = compile_b(source, strict=True)
    result = check_joint(program.ir, request)
    assert (result["status"], result["checked_pairs"]) == ("passed", 25)
    one_tick = {**request, "where": "left_mode == right_mode and right_a == left_a + 1 and right_b == left_b + 1"}
    violation = check_joint(program.ir, one_tick)
    assert violation["status"] == "violated"
    assert violation["witness"]["left"]["inputs"]["mode"] == 1
    assert violation["witness"]["right"]["inputs"]["mode"] == 1


def test_a_directed_reference_value_can_detect_reversed_displacement():
    source = (EXAMPLES / "displacement.bee").read_text()
    request = json.loads((EXAMPLES / "shifts.json").read_text())
    directed = "coordinate(b, mode) - coordinate(a, mode)"
    reversed_direction = "coordinate(a, mode) - coordinate(b, mode)"
    for body, expected in ((directed, 2), (reversed_direction, -2)):
        compiled = compile_b(source.replace(directed, body), strict=True)
        assert check_joint(compiled.ir, request)["status"] == "passed"
        names = {}
        exec(compiled.code, names)
        assert names["displacement"](0, 2, 0) == expected


def test_both_dispatch_registers_keep_the_first_match_at_the_boundary():
    source = (EXAMPLES / "dispatch.bee").read_text()
    for form in ("cases", "ordinary"):
        declaration = function_view(source, "route", form)
        names = {}
        exec(compile_b(declaration, strict=True).code, names)
        assert [names["route"](n) for n in (-1, 0, 1, 3, 4)] == [
            "overdue", "today", "priority", "priority", "standard"
        ]
