from __future__ import annotations

import json
import posixpath
import re
import sys
from dataclasses import dataclass
from typing import Literal, Mapping, Sequence, TypedDict
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
KB_PER_MB: float = 1024.0

SizeTier = Literal["tiny", "standard", "large", "oversize"]


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

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            return f"{base}-{'.'.join(self.prerelease)}"
        return base


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


@dataclass(frozen=True)
class ArtifactEvaluation:
    eligible: bool
    exempt: bool
    oversize: bool
    version: SemVer | None = None


class ReleaseSummary(TypedDict):
    total: int
    eligible: int
    oversize: int
    total_kb: int
    max_kb: int
    consecutive_rejects: int
    freeze: bool
    exempt: int
    eligible_kb: int
    within_budget: bool
    recommended: str | None


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


def classify_size_tier(size_kb: int) -> SizeTier:
    if size_kb < 100:
        return "tiny"
    if size_kb <= 1000:
        return "standard"
    if size_kb <= 5000:
        return "large"
    return "oversize"


def evaluate_artifact(
    artifact: Artifact, min_range: CaretRange | None
) -> ArtifactEvaluation:
    oversize = classify_size_tier(artifact.size_kb) == "oversize"
    if oversize:
        return ArtifactEvaluation(eligible=False, exempt=False, oversize=True)

    norm = normalize_artifact_path(artifact.raw_path)
    if NORM_PATH_RE.fullmatch(norm) is None:
        return ArtifactEvaluation(eligible=False, exempt=False, oversize=False)
    if artifact.channel not in VALID_CHANNELS:
        return ArtifactEvaluation(eligible=False, exempt=False, oversize=False)

    pkg = posixpath.dirname(norm)
    ver_str = posixpath.basename(norm)
    version = parse_semver(ver_str)
    if version is None:
        return ArtifactEvaluation(eligible=False, exempt=False, oversize=False)

    satisfies_range = min_range is not None and min_range.satisfies(version)
    lts_security_exempt = (
        artifact.channel == "lts"
        and "security" in pkg
        and not version.is_prerelease
    )

    eligible = satisfies_range or lts_security_exempt
    exempt = lts_security_exempt and not satisfies_range
    return ArtifactEvaluation(
        eligible=eligible, exempt=exempt, oversize=False, version=version
    )


def parse_input(payload: object) -> tuple[str, float, list[Artifact]]:
    if not isinstance(payload, Mapping):
        raise ValueError("Input root must be a JSON object")

    min_range_raw = payload.get("min_range")
    budget_mb_raw = payload.get("budget_mb")
    artifacts_raw = payload.get("artifacts")
    if not isinstance(min_range_raw, str):
        raise ValueError("min_range must be a string")
    if isinstance(budget_mb_raw, bool) or not isinstance(budget_mb_raw, (int, float)):
        raise ValueError("budget_mb must be a number")
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

    return min_range_raw, float(budget_mb_raw), artifacts


def evaluate_release(
    min_range_expr: str, budget_mb: float, artifacts: Sequence[Artifact]
) -> ReleaseSummary:
    caret_range = parse_caret_range(min_range_expr)

    evaluations = [evaluate_artifact(artifact, caret_range) for artifact in artifacts]
    total = len(artifacts)
    eligible = sum(1 for ev in evaluations if ev.eligible)
    oversize = sum(1 for ev in evaluations if ev.oversize)
    exempt = sum(1 for ev in evaluations if ev.exempt)
    total_kb = sum(artifact.size_kb for artifact in artifacts)
    max_kb = max((artifact.size_kb for artifact in artifacts), default=0)
    eligible_kb = sum(
        artifact.size_kb
        for artifact, ev in zip(artifacts, evaluations)
        if ev.eligible
    )
    within_budget = eligible_kb <= budget_mb * KB_PER_MB
    consecutive_rejects = sum(
        1
        for prev, curr in zip(evaluations, evaluations[1:])
        if not prev.eligible and not curr.eligible
    )
    freeze = consecutive_rejects >= 2
    eligible_versions = [
        ev.version
        for ev in evaluations
        if ev.eligible and ev.version is not None and not ev.version.is_prerelease
    ]
    highest_version = max(eligible_versions, key=lambda v: v.core, default=None)
    recommended = str(highest_version) if highest_version is not None else None

    return {
        "total": total,
        "eligible": eligible,
        "oversize": oversize,
        "total_kb": total_kb,
        "max_kb": max_kb,
        "consecutive_rejects": consecutive_rejects,
        "freeze": freeze,
        "exempt": exempt,
        "eligible_kb": eligible_kb,
        "within_budget": within_budget,
        "recommended": recommended,
    }


def main() -> None:
    payload: object = json.loads(sys.stdin.read())
    min_range_expr, budget_mb, artifacts = parse_input(payload)
    result = evaluate_release(min_range_expr, budget_mb, artifacts)
    sys.stdout.write(json.dumps(result) + "\n")


if __name__ == "__main__":
    main()
