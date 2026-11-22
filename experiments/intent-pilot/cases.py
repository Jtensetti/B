"""Frozen product-owner answers and downstream source edits, independent of the selectors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

Point = tuple[int, ...]
Policy = Callable[[Point, int], bool]


@dataclass(frozen=True)
class Product:
    name: str
    parameters: tuple[str, ...]
    declarations: str
    default: str
    calibration: tuple[Point, ...]
    later: tuple[Point, ...]
    outputs: tuple[int, ...]
    defaults: Callable[[Point], int]
    alternatives: tuple[str, ...]
    cards: tuple[tuple[Point, int, str], ...]
    owner: Callable[[str, Point, int], bool]
    undocumented_witness: tuple[Point, int]
    edits: dict[str, str]


def label_owner(world: str, point: Point, value: int) -> bool:
    level, = point
    default = level + 2
    if value == default:
        return True
    if world == "unlisted":
        # Both flexibilities in the calibration area; neither on later pages.
        # The product owner also permits a wide fold at two specified insertions.
        if level in (1, 4) and value == level + 4:
            return True
        return level < 2 and abs(value - default) == 1
    if value == default - 1:
        return world in ("tighten", "flexible")
    if value == default + 1:
        return world in ("loosen", "flexible")
    return False


def nav_owner(world: str, point: Point, value: int) -> bool:
    index, keyboard = point
    if value == index:
        return True
    if world == "unlisted":
        # Middle tabs reset to the corresponding edge. At the ends, the product
        # instead permits a jump to the second tab for pointer navigation.
        if index == 1 and keyboard and value == 2:
            return True
        if index in (1, 2):
            return value == (0 if keyboard else 3)
        return index == 3 and not keyboard and value == 1
    if keyboard and value == 0:
        return world in ("home", "both-edges")
    if not keyboard and value == 3:
        return world in ("end", "both-edges")
    return False


LABEL = Product(
    "labels", ("level",), "level: Int", "level + 2",
    ((0,), (1,)), ((2,), (3,), (4,)), tuple(range(9)), lambda p: p[0] + 2,
    ("fixed", "tighten", "loosen", "flexible"),
    (((1,), 2, "On page level 1, may the designer choose a gap of 2?"),
     ((1,), 4, "On page level 1, may the designer choose a gap of 4?")),
    label_owner, ((1,), 5),
    {
        "rewrite": "2 + level",
        "tighter-later": "if level >= 2 then level + 1 else level + 2",
        "looser-later": "if level >= 2 then level + 3 else level + 2",
        "split-layout": "if level == 2 then level + 1 else if level > 2 then level + 3 else level + 2",
        "wide-last-fold": "if level == 4 then level + 4 else level + 2",
        "wide-middle-fold": "if level == 2 then level + 4 else level + 2",
    },
)
NAV = Product(
    "tabs", ("index", "keyboard"), "index: Int, keyboard: Int", "index",
    tuple((i,k) for i in (1, 2) for k in (0, 1)), tuple((i,k) for i in (0, 3) for k in (0, 1)),
    tuple(range(4)), lambda p: p[0], ("stay", "home", "end", "both-edges"),
    (((2, 1), 0, "With keyboard navigation on tab 2, may focus return to tab 0?"),
     ((1, 0), 3, "With pointer navigation on tab 1, may focus move to tab 3?")),
    nav_owner, ((1, 1), 2),
    {
        "rewrite": "index + 0",
        "keyboard-home": "if index == 3 and keyboard == 1 then 0 else index",
        "pointer-end": "if index == 0 and keyboard == 0 then 3 else index",
        "two-edges": "if index == 3 and keyboard == 1 then 0 else if index == 0 and keyboard == 0 then 3 else index",
        "pointer-shortcut": "if index == 3 and keyboard == 0 then 1 else index",
        "keyboard-shortcut": "if index == 0 and keyboard == 1 then 2 else index",
    },
)
PRODUCTS = (LABEL, NAV)
