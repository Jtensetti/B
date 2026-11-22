"""Typed Python policy comparison, independent of B, the owner and the edit oracle."""
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import product

Point = tuple[int, ...]
Query = tuple[Point, int]
Answer = tuple[Point, int, bool]


def permits(product_name: str, policy: str, point: Point, candidate: int) -> bool:
    if product_name == "labels":
        level, = point
        offsets = {"fixed": (2, 2), "tighten": (1, 2), "loosen": (2, 3), "flexible": (1, 3)}
        low, high = offsets[policy]
        return level + low <= candidate <= level + high

    index, keyboard = point
    if policy == "stay":
        allowed = {index}
    elif policy == "home":
        allowed = {index, 0} if keyboard == 1 else {index}
    elif policy == "end":
        allowed = {index, 3} if keyboard == 0 else {index}
    elif policy == "both-edges":
        allowed = {index, 0 if keyboard == 1 else 3}
    else:
        raise KeyError(policy)
    return candidate in allowed


@dataclass(frozen=True)
class Response:
    survivors: tuple[str, ...]
    question: Query | None


def choose(product_name: str, policies: Sequence[str], calibration: Sequence[Point],
           values: Sequence[int], evidence: Sequence[Answer]) -> Response:
    live = tuple(p for p in policies if all(
        permits(product_name, p, point, value) == allowed for point, value, allowed in evidence))
    cells = list(product(calibration, values))
    models = {tuple(permits(product_name, p, *cell) for cell in cells) for p in live}
    ranked = []
    for i, (point, value) in enumerate(cells):
        yes = sum(model[i] for model in models)
        minority = min(yes, len(models) - yes)
        if minority:
            coordinates = (*point, value)
            ranked.append(((-minority, sum(map(abs, coordinates)), tuple(map(abs, coordinates)), coordinates),
                           (point, value)))
    return Response(live, min(ranked)[1] if ranked else None)


def fixed_card(product_name: str, live: Sequence[str], cards: Iterable[Query]) -> Query | None:
    for point, value in cards:
        if len({permits(product_name, p, point, value) for p in live}) == 2:
            return point, value
    return None


def edited(product_name: str, revision: str, point: Point) -> int:
    if product_name == "labels":
        level, = point
        offset = 2
        if revision == "tighter-later" and level >= 2:
            offset = 1
        elif revision == "looser-later" and level >= 2:
            offset = 3
        elif revision == "split-layout" and level >= 2:
            offset = 1 if level == 2 else 3
        elif revision == "wide-last-fold" and level == 4:
            offset = 4
        elif revision == "wide-middle-fold" and level == 2:
            offset = 4
        return level + offset

    index, keyboard = point
    if revision in ("keyboard-home", "two-edges") and (index, keyboard) == (3, 1):
        return 0
    if revision in ("pointer-end", "two-edges") and (index, keyboard) == (0, 0):
        return 3
    if revision == "pointer-shortcut" and (index, keyboard) == (3, 0):
        return 1
    if revision == "keyboard-shortcut" and (index, keyboard) == (0, 1):
        return 2
    return index
