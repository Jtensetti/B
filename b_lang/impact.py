"""Compare checked obligations across program revisions.

Locations within a caller are structural. A unique unchanged expression and
contract origin can identify a relocation. Repeated indistinguishable sites
cannot be aligned across different locations.
"""
from __future__ import annotations

from collections import defaultdict

from .composition import Analysis, Obligation


def _location(item: Obligation) -> tuple:
    return item.caller, item.site, item.kind, item.target


def _content(item: Obligation) -> tuple:
    return (item.caller, item.kind, item.target, item.requirement,
            item.expression, item.dependencies)


def _locations_by_content(items: dict) -> dict:
    groups = defaultdict(list)
    for location, item in items.items():
        groups[_content(item)].append(location)
    return groups


def _pairs(before: Analysis, after: Analysis):
    old = {_location(item): item for item in before.obligations}
    new = {_location(item): item for item in after.obligations}

    for location in sorted(old.keys() & new.keys()):
        if _content(old[location]) == _content(new[location]):
            yield old.pop(location), new.pop(location), "site-and-expression"

    # Anchor the unambiguous unchanged locations first. Only align a remaining
    # expression across locations when there is exactly one candidate on each side.
    old_groups, new_groups = _locations_by_content(old), _locations_by_content(new)
    for content, old_locations in old_groups.items():
        new_locations = new_groups.get(content, ())
        if len(old_locations) == len(new_locations) == 1:
            yield old.pop(old_locations[0]), new.pop(new_locations[0]), "expression"

    # Edits to the obligation or its dependencies may alter the content itself.
    # These pairs have only the original structural site as evidence of identity.
    for location in sorted(old.keys() & new.keys()):
        yield old.pop(location), new.pop(location), "site"
    for location in sorted(old):
        yield old[location], None, None
    for location in sorted(new):
        yield None, new[location], None


def compare(before: Analysis, after: Analysis) -> dict:
    changes = []
    unchanged = 0
    for previous, current, matched_by in _pairs(before, after):
        if previous == current:
            unchanged += 1
            continue
        moved = previous is not None and current is not None and previous.site != current.site
        if previous is None:
            change = "added"
        elif current is None:
            change = "removed"
        elif previous.status == "proved" and current.status != "proved":
            change = "lost-proof"
        elif previous.status != "proved" and current.status == "proved":
            change = "gained-proof"
        elif moved and previous.status == current.status:
            change = "moved"
        else:
            change = "changed"
        changes.append({
            "change": change,
            "before": previous.to_dict() if previous else None,
            "after": current.to_dict() if current else None,
            "moved": moved,
            "matched_by": matched_by,
        })
    return {"schema": "b-contract-impact", "version": 1, "unchanged": unchanged, "changes": changes}
