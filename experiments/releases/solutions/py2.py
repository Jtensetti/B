#!/usr/bin/env python3
"""Read {"releases": [...]} from stdin and print the latest stable release per package."""

import datetime
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

# Semver 2.0.0 grammar: major.minor.patch, optional -prerelease, optional +build.
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def stable_key(version: str) -> Optional[Tuple[int, int, int]]:
    """Return the comparison key for a stable version, or None if it is a prerelease.

    Build metadata (after '+') is ignored for ordering, as in npm semver.
    Only stable versions are compared, so the prerelease ordering rules never apply.
    """
    match = SEMVER_RE.match(version)
    if match is None:
        raise ValueError(f"invalid semver version: {version!r}")
    if match.group(4) is not None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def latest_stable(releases: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """Map each package to its highest stable release; packages without one are omitted.

    Output order follows the first appearance of each package in the input.
    On an exact version tie, the first release in the input wins.
    """
    order: List[str] = []
    best: Dict[str, Tuple[Tuple[int, int, int], str, str]] = {}
    for release in releases:
        name: str = release["package"]
        if name not in order:
            order.append(name)
        key = stable_key(release["version"])
        if key is None:
            continue
        current = best.get(name)
        if current is None or key > current[0]:
            best[name] = (key, release["version"], release["date"])
    return {
        name: {"version": best[name][1], "date": best[name][2]}
        for name in order
        if name in best
    }


def weekly_counts(releases: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count releases per ISO 8601 week, keyed "YYYY-Www" using the ISO week-numbering year.

    Keys are returned in chronological order.
    """
    counts: Dict[str, int] = {}
    for release in releases:
        date = datetime.date.fromisoformat(release["date"])
        iso_year, iso_week, _ = date.isocalendar()
        key = f"{iso_year:04d}-W{iso_week:02d}"
        counts[key] = counts.get(key, 0) + 1
    return {key: counts[key] for key in sorted(counts)}


def stale_packages(
    latest: Dict[str, Dict[str, str]], today: str, stale_days: int
) -> List[str]:
    """Return, sorted, the packages whose latest stable release is more than stale_days before today."""
    today_date = datetime.date.fromisoformat(today)
    stale: List[str] = []
    for name, info in latest.items():
        age = today_date - datetime.date.fromisoformat(info["date"])
        if age.days > stale_days:
            stale.append(name)
    return sorted(stale)


def watched_versions(
    releases: List[Dict[str, Any]], watch: Dict[str, str]
) -> Dict[str, str]:
    """For each watched package, the highest released version satisfying its npm semver range.

    The range matching is done by the npm semver package (see watch_range.js next to
    this file), so it follows npm's rules exactly. Packages with no satisfying release
    are omitted.
    """
    if not watch:
        return {}
    versions: Dict[str, List[str]] = {}
    for release in releases:
        versions.setdefault(release["package"], []).append(release["version"])
    request = json.dumps({"versions": versions, "watch": watch})
    helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watch_range.js")
    proc = subprocess.run(
        ["node", helper],
        input=request,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def major_counts(releases: List[Dict[str, Any]]) -> Dict[str, int]:
    """For each package with a stable release, the number of distinct major versions among them."""
    majors: Dict[str, set] = {}
    for release in releases:
        key = stable_key(release["version"])
        if key is None:
            continue
        majors.setdefault(release["package"], set()).add(key[0])
    return {name: len(found) for name, found in majors.items()}


def main() -> None:
    data: Dict[str, Any] = json.load(sys.stdin)
    releases: List[Dict[str, Any]] = data.get("releases", [])
    latest = latest_stable(releases)
    stale: List[str] = []
    if "today" in data and "stale_days" in data:
        stale = stale_packages(latest, data["today"], int(data["stale_days"]))
    watch: Dict[str, str] = data.get("watch") or {}
    result = {
        "latest": latest,
        "weekly": weekly_counts(releases),
        "stale": stale,
        "watched": watched_versions(releases, watch),
        "majors": major_counts(releases),
    }
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
