The program reads one line of JSON from standard input and writes one line of JSON to standard output.

Input: {"releases": [{"package", "version", "date": "YYYY-MM-DD"}, ...], "today": "YYYY-MM-DD", "stale_days": int, "watch": {"<package>": "<npm range>"} (optional)}

Output keys:
- latest: per package, the highest stable version under npm semver ordering (no prerelease tag) and its date; packages with only prereleases are left out.
- weekly: number of releases per ISO week "YYYY-Www" (ISO week-numbering year).
- stale: packages whose latest stable release is more than stale_days days before today, sorted.
- watched: per watched package, the highest released version satisfying the npm range (semver maxSatisfying, default options); packages without a match are left out.
- majors: per package with a stable release, the number of distinct major versions among its stable releases.
