"""Bounded exact minimax planning for a finite catalog of binary policy answers."""
from functools import cache

MAX_CLASSES = 10
MAX_PARTITIONS = 32


def _costs(patterns, full):
    @cache
    def depth(state):
        if state.bit_count() <= 1:
            return 0
        # Distinct observable rows differ in at least one column. Querying
        # such a column strictly reduces both recursive subproblems.
        costs = []
        for pattern in patterns:
            yes = state & pattern
            no = state ^ yes
            if yes and no:
                costs.append(1 + max(depth(yes), depth(no)))
        return min(costs)

    return {p: 1 + max(depth(p), depth(full ^ p)) for p in patterns}


def minimax_question(cells, class_masks, skipped, status):
    """Return (chosen index, planning metadata), or use the caller's balanced fallback."""
    # Skipping a cell can make two previously different classes impossible to
    # tell apart. Count and optimize only distinctions still observable.
    available = ((1 << len(cells)) - 1) ^ sum(1 << i for i in skipped)
    observable = sorted({m & available for m in class_masks})
    count = len(observable)
    meaningful = status not in ("empty-domain", "inconsistent")
    complete = count == len(class_masks) if meaningful else None
    plan = {
        "requested": "minimax", "used": "minimax",
        "goal": "distinguish remaining policy behaviors on unskipped grid cells",
        "assumptions": ["true policy in catalog", "truthful decisive future answers", "unit cost per answer"],
        "remaining_full_classes": len(class_masks), "observable_classes": count,
        "full_class_identification_possible": complete,
        "worst_case_remaining_questions": None, "observable_worst_case_remaining_questions": None,
        "limits": {"observable_classes": MAX_CLASSES, "distinct_partitions": MAX_PARTITIONS},
    }
    if not meaningful:
        return None, plan
    if count <= 1:
        plan["observable_worst_case_remaining_questions"] = 0
        plan["worst_case_remaining_questions"] = 0 if complete else None
        return None, plan
    if count > MAX_CLASSES:
        return None, {**plan, "used": "balanced", "reason": "observable-class-limit"}

    full = (1 << count) - 1
    representatives = {}
    for index, (point, output) in enumerate(cells):
        if index in skipped:
            continue
        pattern = sum(((mask >> index) & 1) << row for row, mask in enumerate(observable))
        if pattern in (0, full):
            continue
        # Complementary columns induce identical subproblems. Preserve the
        # simplest available actual question for presentation.
        partition = min(pattern, full ^ pattern)
        coordinates = (*point, output)
        magnitudes = tuple(map(abs, coordinates))
        key = (sum(magnitudes), magnitudes, coordinates)
        if partition not in representatives or key < representatives[partition][0]:
            representatives[partition] = (key, index)
            if len(representatives) > MAX_PARTITIONS:
                return None, {**plan, "used": "balanced", "reason": "distinct-partition-limit"}

    costs = _costs(tuple(representatives), full)
    best = min(costs, key=lambda p: (costs[p], -min(p.bit_count(), count - p.bit_count()),
                                     representatives[p][0]))
    depth = costs[best]
    plan.update(distinct_partitions=len(representatives), observable_worst_case_remaining_questions=depth,
                worst_case_remaining_questions=depth if complete else None)
    return representatives[best][1], plan
