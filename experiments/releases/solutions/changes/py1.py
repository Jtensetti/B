#!/usr/bin/env python3
"""Report the latest stable release of each package.

Reads one JSON line from stdin: {"releases": [{"package", "version", "date"}, ...]}
Writes one JSON line to stdout: {"latest": {"<package>": {"version", "date"}, ...}}

A version is stable when its core (the part before any "+" build metadata)
has no "-" prerelease tag. Among stable versions the highest by semver
precedence wins; build metadata is ignored for precedence, as in semver 7.
"""

import datetime
import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional, Tuple

# Node script that applies npm's semver.maxSatisfying (semver@7, default options).
# Reads {"<package>": {"range": "...", "versions": [...]}} on stdin and prints
# {"<package>": "<version>" | null} on stdout.
NODE_WATCH_SCRIPT = """
const semver = require(process.argv[1]);
let input = '';
process.stdin.on('data', (d) => { input += d; });
process.stdin.on('end', () => {
  const jobs = JSON.parse(input);
  const out = {};
  for (const pkg of Object.keys(jobs)) {
    const best = semver.maxSatisfying(jobs[pkg].versions, jobs[pkg].range);
    out[pkg] = best === null ? null : best;
  }
  process.stdout.write(JSON.stringify(out));
});
"""


def find_watched(releases: list[Dict[str, Any]], watch: Dict[str, str]) -> Dict[str, str]:
    """Return the highest released version satisfying each watched range, omitting unmatched ones."""
    if not watch:
        return {}
    versions: Dict[str, list[str]] = {}
    for release in releases:
        versions.setdefault(release["package"], []).append(release["version"])
    jobs: Dict[str, Dict[str, Any]] = {
        package: {"range": rng, "versions": versions.get(package, [])}
        for package, rng in watch.items()
    }
    semver_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "node_modules", "semver")
    completed = subprocess.run(
        ["node", "-e", NODE_WATCH_SCRIPT, semver_path],
        input=json.dumps(jobs),
        capture_output=True,
        text=True,
        check=True,
    )
    matched: Dict[str, Optional[str]] = json.loads(completed.stdout)
    return {package: version for package, version in matched.items() if version is not None}


def parse_stable_core(version: str) -> Optional[Tuple[int, int, int]]:
    """Return (major, minor, patch) for a stable version, or None if it is a prerelease."""
    core = version.split("+", 1)[0]
    if "-" in core:
        return None
    major, minor, patch = core.split(".")
    return int(major), int(minor), int(patch)


def pick_latest(releases: list[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """Return the latest stable release per package, in first-seen package order."""
    # Each entry maps a package to (core, date, version) of its best candidate so far.
    best: Dict[str, Tuple[Tuple[int, int, int], str, str]] = {}
    for release in releases:
        package: str = release["package"]
        version: str = release["version"]
        date: str = release["date"]
        core = parse_stable_core(version)
        if core is None:
            continue
        candidate = (core, date, version)
        current = best.get(package)
        if current is None or candidate > current:
            best[package] = candidate
    return {
        package: {"version": version, "date": date}
        for package, (_, date, version) in best.items()
    }


def count_per_iso_week(releases: list[Dict[str, Any]]) -> Dict[str, int]:
    """Return the number of stable releases per ISO week, keyed "YYYY-Www", in chronological order.

    Prerelease versions are not counted. Weeks with no stable release are omitted.
    """
    counts: Dict[str, int] = {}
    for release in releases:
        if parse_stable_core(release["version"]) is None:
            continue
        year, week, _ = datetime.date.fromisoformat(release["date"]).isocalendar()
        key = f"{year:04d}-W{week:02d}"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def count_majors(releases: list[Dict[str, Any]]) -> Dict[str, int]:
    """Return, per package with a stable release, the number of distinct major versions."""
    majors: Dict[str, set[int]] = {}
    for release in releases:
        core = parse_stable_core(release["version"])
        if core is None:
            continue
        majors.setdefault(release["package"], set()).add(core[0])
    return {package: len(numbers) for package, numbers in majors.items()}


def find_stale(
    latest: Dict[str, Dict[str, str]],
    today: str,
    stale_days: int,
    stale_overrides: Optional[Dict[str, int]] = None,
) -> list[str]:
    """Return, sorted, the packages whose latest release is more than their threshold before today.

    A package listed in stale_overrides uses its own number of days; all others use stale_days.
    """
    overrides = stale_overrides or {}
    today_date = datetime.date.fromisoformat(today)
    stale: list[str] = []
    for package, release in latest.items():
        threshold = int(overrides.get(package, stale_days))
        age = today_date - datetime.date.fromisoformat(release["date"])
        if age.days > threshold:
            stale.append(package)
    return sorted(stale)


def find_since(latest: Dict[str, Dict[str, str]], today: str) -> Dict[str, int]:
    """Return, per package in latest, the calendar days from its latest release to today."""
    today_date = datetime.date.fromisoformat(today)
    return {
        package: (today_date - datetime.date.fromisoformat(release["date"])).days
        for package, release in latest.items()
    }


def main() -> None:
    data: Dict[str, Any] = json.loads(sys.stdin.read())
    releases: list[Dict[str, Any]] = data.get("releases", [])
    if "today" in data:
        # Releases dated after today are treated as if they were not in the input.
        today_iso = datetime.date.fromisoformat(data["today"]).isoformat()
        releases = [r for r in releases if r["date"] <= today_iso]
    latest = pick_latest(releases)
    stale: list[str] = []
    if "today" in data and "stale_days" in data:
        overrides: Dict[str, int] = data.get("stale_overrides", {})
        stale = find_stale(latest, data["today"], int(data["stale_days"]), overrides)
    watch: Dict[str, str] = data.get("watch", {})
    since: Dict[str, int] = {}
    if "today" in data:
        since = find_since(latest, data["today"])
    result = {
        "latest": latest,
        "since": since,
        "weekly": count_per_iso_week(releases),
        "stale": stale,
        "watched": find_watched(releases, watch),
        "majors": count_majors(releases),
    }
    sys.stdout.write(json.dumps(result, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
