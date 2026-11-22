"""Compare finite relational checks with simpler designs and independent expected outputs."""
import json
from collections.abc import Callable
from itertools import combinations, product

from b_lang.compiler import compile_b
from b_lang.joint import check_joint


RANKS = (0, 1, 2)
SCREENS = (0, 1)  # dashboard, export
COMPACT, EXPANDED = (1, 2, 3), (2, 3, 4)
TICKS = (-2, -1, 0, 1, 2)  # integer half-pixels


def build(source):
    compiled = compile_b(source)
    functions = {}
    exec(compiled.code, functions)
    return compiled.ir, functions


def python_uniform(gap: Callable[[int, int], int]) -> bool:
    """A typed Python property test on the same B program's normal public returns."""
    return all(gap(screen, j) - gap(screen, i) == j - i
               for screen in SCREENS for i, j in combinations(RANKS, 2))


def layout_case(expand_dashboard, compact_export, stale_dashboard_default=False):
    dashboard_style = int(expand_dashboard and not stale_dashboard_default)
    export_style = int(not compact_export)
    row_style = "default_style(screen)"
    if compact_export:
        # The export change includes a fast path for the old compact dashboard header.
        row_style = "if screen == 0 and rank == 0 then 0 else default_style(screen)"
    ir, fn = build(f"""
fn default_style(screen: Int) -> Int pure = if screen == 0 then {dashboard_style} else {export_style}
fn paint(rank: Int, style: Int) -> Int pure = rank + 1 + style
fn rendered_gap(screen: Int, rank: Int) -> Int pure = paint(rank, {row_style})
fn assemble(style: Int) -> List[Int] pure = [paint(0, style), paint(1, style), paint(2, style)]
fn shared_layout(screen: Int) -> List[Int] pure = assemble(default_style(screen))
""")
    frames = [tuple(fn["rendered_gap"](screen, rank) for rank in RANKS) for screen in SCREENS]
    with_shared_style = [tuple(fn["shared_layout"](screen)) for screen in SCREENS]
    expected = [EXPANDED if expand_dashboard else COMPACT, COMPACT if compact_export else EXPANDED]
    joint = check_joint(ir, {
        "left": {"function": "rendered_gap", "axes": {"screen": SCREENS, "rank": RANKS}},
        "where": "left_screen == right_screen and left_rank < right_rank",
        "ensures": "left_result - left_rank == right_result - right_rank",
    })
    pair_test = python_uniform(fn["rendered_gap"])
    pointwise = all(gap in (rank + 1, rank + 2) for frame in frames for rank, gap in enumerate(frame))
    whole_screen = all(frame in (COMPACT, EXPANDED) for frame in frames)
    assert joint["status"] in ("passed", "violated")
    assert (joint["status"] == "passed") == pair_test
    assert (pointwise and pair_test) == whole_screen
    return {
        "renderer_frames": frames, "per_row": pointwise, "typed_python_pairs": pair_test,
        "joint_B": joint["status"], "first_joint_witness": joint.get("witness"),
        "whole_layout_allowed": whole_screen, "requested_defaults": frames == expected,
        "shared_layout_allowed": all(f in (COMPACT, EXPANDED) for f in with_shared_style),
        "shared_requested_defaults": with_shared_style == expected,
    }


def python_shifted(move: Callable[[int, int], int], shift: int) -> bool:
    return all(move(a + shift, b + shift) == move(a, b)
               for a, b in product(TICKS, repeat=2) if a + shift in TICKS and b + shift in TICKS)


def motion_cases():
    bodies = {
        "signed_displacement": "finish - start",
        "wrong_sign": "start - finish",
        "stuck": "0",
        "absolute_endpoint": "finish",
        "snap_endpoints": "(finish - (finish % 2)) - (start - (start % 2))",
        "snap_difference": "(finish - start) - ((finish - start) % 2)",
    }
    # The table is the display owner's independent pixel-boundary specification.
    displayed = {-2: -2, -1: -2, 0: 0, 1: 0, 2: 2}
    checked = {}
    for name, body in bodies.items():
        ir, ns = build(f"fn move(start: Int, finish: Int) -> Int pure = {body}")
        move = ns["move"]
        row = {}
        for shift in (1, 2):
            joint = check_joint(ir, {
                "left": {"function": "move", "axes": {"start": TICKS, "finish": TICKS}},
                "where": f"right_start == left_start + {shift} and right_finish == left_finish + {shift}",
                "ensures": "left_result == right_result",
            })
            holds = python_shifted(move, shift)
            assert joint["status"] == ("passed" if holds else "violated")
            row[f"shift_{shift}_ticks"] = {"status": joint["status"], "witness": joint.get("witness")}
        row["ideal_correct_of_25"] = sum(move(a, b) == b - a for a, b in product(TICKS, repeat=2))
        row["pixel_correct_of_25"] = sum(move(a, b) == displayed[b] - displayed[a] for a, b in product(TICKS, repeat=2))
        checked[name] = row
    return checked


def measure():
    layouts = {
        "original": layout_case(False, False),
        "expand_dashboard": layout_case(True, False),
        "compact_export_and_cache_header": layout_case(False, True),
        "combined": layout_case(True, True),
        "requested_expansion_missing": layout_case(True, False, stale_dashboard_default=True),
    }
    return {"layouts": layouts, "motion": motion_cases()}


if __name__ == "__main__":
    print(json.dumps(measure(), indent=2))
