from __future__ import annotations

import json
import posixpath
import re
import sys
from dataclasses import dataclass
from typing import Mapping, Sequence
from urllib.parse import unquote

VALID_CHANNELS: frozenset[str] = frozenset({"stable", "beta", "lts"})
NORM_PATH_RE: re.Pattern[str] = re.compile(
    r"[a-z0-9-]+/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?"
)
SEMVER_RE: re.Pattern[str] = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z.-]+))?"
)
NUMERIC_IDENT_RE: re.Pattern[str] = re.compile(r"[0-9]+")
IDENT_RE: re.Pattern[str] = re.compile(r"[0-9A-Za-z-]+")


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    @property
    def core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    @property
    def is_prerelease(self) -> bool:
        return len(self.prerelease) > 0


@dataclass(frozen=True)
class CaretRange:
    lower: tuple[int, int, int]
    upper: tuple[int, int, int]

    def satisfies(self, version: SemVer) -> bool:
        if version.is_prerelease:
            return False
        return self.lower <= version.core < self.upper


@dataclass(frozen=True)
class Artifact:
    raw_path: str
    channel: str
    size_kb: int


def parse_semver(text: str) -> SemVer | None:
    match = SEMVER_RE.fullmatch(text)
    if match is None:
        return None

    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3))
    prerelease_raw = match.group(4)

    if prerelease_raw is None:
        return SemVer(major=major, minor=minor, patch=patch)

    identifiers = prerelease_raw.split(".")
    for ident in identifiers:
        if not ident or IDENT_RE.fullmatch(ident) is None:
            return None
        if NUMERIC_IDENT_RE.fullmatch(ident) is not None and len(ident) > 1 and ident.startswith("0"):
            return None

    return SemVer(major=major, minor=minor, patch=patch, prerelease=tuple(identifiers))


def parse_caret_range(range_expr: str) -> CaretRange | None:
    stripped = range_expr.strip()
    if not stripped.startswith("^"):
        return None

    base = parse_semver(stripped[1:])
    if base is None or base.is_prerelease:
        return None

    lower = base.core
    if base.major > 0:
        upper = (base.major + 1, 0, 0)
    elif base.minor > 0:
        upper = (0, base.minor + 1, 0)
    else:
        upper = (0, 0, base.patch + 1)

    return CaretRange(lower=lower, upper=upper)


def normalize_artifact_path(raw_path: str) -> str:
    decoded = unquote(raw_path)
    return posixpath.normpath(decoded)


def is_eligible(artifact: Artifact, min_range: CaretRange | None) -> bool:
    if min_range is None:
        return False

    norm = normalize_artifact_path(artifact.raw_path)
    if NORM_PATH_RE.fullmatch(norm) is None:
        return False
    if artifact.channel not in VALID_CHANNELS:
        return False

    ver_str = posixpath.basename(norm)
    version = parse_semver(ver_str)
    if version is None:
        return False

    return min_range.satisfies(version)


def parse_input(payload: object) -> tuple[str, list[Artifact]]:
    if not isinstance(payload, Mapping):
        raise ValueError("Input root must be a JSON object")

    min_range_raw = payload.get("min_range")
    artifacts_raw = payload.get("artifacts")
    if not isinstance(min_range_raw, str):
        raise ValueError("min_range must be a string")
    if not isinstance(artifacts_raw, Sequence) or isinstance(artifacts_raw, (str, bytes)):
        raise ValueError("artifacts must be a list")

    artifacts: list[Artifact] = []
    for item in artifacts_raw:
        if not isinstance(item, Mapping):
            raise ValueError("Each artifact must be a JSON object")
        raw_path = item.get("raw_path")
        channel = item.get("channel")
        size_kb = item.get("size_kb")
        if not isinstance(raw_path, str) or not isinstance(channel, str):
            raise ValueError("raw_path and channel must be strings")
        if isinstance(size_kb, bool) or not isinstance(size_kb, int):
            raise ValueError("size_kb must be an integer")
        artifacts.append(Artifact(raw_path=raw_path, channel=channel, size_kb=size_kb))

    return min_range_raw, artifacts


def evaluate_release(min_range_expr: str, artifacts: Sequence[Artifact]) -> dict[str, int]:
    caret_range = parse_caret_range(min_range_expr)

    total = len(artifacts)
    eligible = sum(1 for artifact in artifacts if is_eligible(artifact, caret_range))
    total_kb = sum(artifact.size_kb for artifact in artifacts)
    max_kb = max((artifact.size_kb for artifact in artifacts), default=0)

    return {
        "total": total,
        "eligible": eligible,
        "total_kb": total_kb,
        "max_kb": max_kb,
    }


def main() -> None:
    payload: object = json.loads(sys.stdin.read())
    min_range_expr, artifacts = parse_input(payload)
    result = evaluate_release(min_range_expr, artifacts)
    sys.stdout.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
