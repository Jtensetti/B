from __future__ import annotations

from dataclasses import dataclass
import json
import posixpath
import re
import sys
from typing import Literal, TypedDict
from urllib.parse import unquote

SizeTier = Literal["tiny", "standard", "large", "oversize"]

VALID_CHANNELS: frozenset[str] = frozenset({"stable", "beta", "lts"})

NORM_PATH_RE: re.Pattern[str] = re.compile(
    r"^[a-z0-9-]+/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?\Z"
)

SEMVER_RE: re.Pattern[str] = re.compile(
    r"^(?P<major>0|[1-9][0-9]*)"
    r"\.(?P<minor>0|[1-9][0-9]*)"
    r"\.(?P<patch>0|[1-9][0-9]*)"
    r"(?:-(?P<prerelease>(?:0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[a-zA-Z-][0-9a-zA-Z-]*))*))?\Z"
)

CARET_RANGE_RE: re.Pattern[str] = re.compile(
    r"^\^(?P<major>0|[1-9][0-9]*)"
    r"\.(?P<minor>0|[1-9][0-9]*)"
    r"\.(?P<patch>0|[1-9][0-9]*)\Z"
)


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()

    @property
    def is_prerelease(self) -> bool:
        return len(self.prerelease) > 0

    @property
    def core_tuple(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)


@dataclass(frozen=True)
class CaretRange:
    major: int
    minor: int
    patch: int

    def upper_bound(self) -> tuple[int, int, int]:
        if self.major > 0:
            return (self.major + 1, 0, 0)
        if self.minor > 0:
            return (0, self.minor + 1, 0)
        return (0, 0, self.patch + 1)

    def satisfies(self, version: SemVer) -> bool:
        if version.is_prerelease:
            return False
        lower = (self.major, self.minor, self.patch)
        upper = self.upper_bound()
        return lower <= version.core_tuple < upper


@dataclass(frozen=True)
class ArtifactInput:
    raw_path: str
    channel: str
    size_kb: int


@dataclass(frozen=True)
class EvaluatedArtifact:
    raw_path: str
    norm_path: str
    pkg: str
    ver: str
    channel: str
    size_kb: int
    size_tier: SizeTier
    valid_format: bool
    semver: SemVer | None
    exempt_used: bool
    eligible: bool


class GateSummary(TypedDict):
    total: int
    eligible: int
    oversize: int
    total_kb: int
    max_kb: int
    consecutive_rejects: int
    freeze: bool
    exempt: int


def parse_semver(text: str) -> SemVer | None:
    match = SEMVER_RE.match(text)
    if match is None:
        return None
    prerelease_raw = match.group("prerelease")
    prerelease = tuple(prerelease_raw.split(".")) if prerelease_raw is not None else ()
    return SemVer(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
        prerelease=prerelease,
    )


def parse_caret_range(spec: str) -> CaretRange | None:
    match = CARET_RANGE_RE.match(spec.strip())
    if match is None:
        return None
    return CaretRange(
        major=int(match.group("major")),
        minor=int(match.group("minor")),
        patch=int(match.group("patch")),
    )


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
    artifact: ArtifactInput,
    min_range: CaretRange | None,
) -> EvaluatedArtifact:
    norm = normalize_artifact_path(artifact.raw_path)
    ver = posixpath.basename(norm)
    pkg = posixpath.dirname(norm)
    size_tier = classify_size_tier(artifact.size_kb)

    valid_format = (
        NORM_PATH_RE.match(norm) is not None and artifact.channel in VALID_CHANNELS
    )
    semver = parse_semver(ver) if valid_format else None
    not_oversize = size_tier != "oversize"
    satisfies_range = (
        valid_format
        and not_oversize
        and semver is not None
        and min_range is not None
        and min_range.satisfies(semver)
    )
    lts_security_exempt = (
        valid_format
        and artifact.channel == "lts"
        and "security" in pkg
        and semver is not None
        and not semver.is_prerelease
        and not_oversize
    )
    exempt_used = lts_security_exempt and not satisfies_range
    eligible = satisfies_range or lts_security_exempt

    return EvaluatedArtifact(
        raw_path=artifact.raw_path,
        norm_path=norm,
        pkg=pkg,
        ver=ver,
        channel=artifact.channel,
        size_kb=artifact.size_kb,
        size_tier=size_tier,
        valid_format=valid_format,
        semver=semver,
        exempt_used=exempt_used,
        eligible=eligible,
    )


def parse_request(raw: object) -> tuple[str, list[ArtifactInput]]:
    if not isinstance(raw, dict):
        raise ValueError("Input must be a JSON object")

    min_range = raw.get("min_range")
    artifacts_raw = raw.get("artifacts")
    if not isinstance(min_range, str) or not isinstance(artifacts_raw, list):
        raise ValueError("Invalid input schema")

    artifacts: list[ArtifactInput] = []
    for item in artifacts_raw:
        if not isinstance(item, dict):
            raise ValueError("Each artifact must be a JSON object")
        raw_path = item.get("raw_path")
        channel = item.get("channel")
        size_kb = item.get("size_kb")
        if (
            not isinstance(raw_path, str)
            or not isinstance(channel, str)
            or not isinstance(size_kb, int)
            or isinstance(size_kb, bool)
        ):
            raise ValueError("Invalid artifact fields")
        artifacts.append(
            ArtifactInput(raw_path=raw_path, channel=channel, size_kb=size_kb)
        )

    return min_range, artifacts


def process_release_gate(
    min_range_spec: str,
    artifacts: list[ArtifactInput],
) -> GateSummary:
    min_range = parse_caret_range(min_range_spec)
    evaluated = [evaluate_artifact(artifact, min_range) for artifact in artifacts]

    total = len(evaluated)
    eligible = sum(1 for item in evaluated if item.eligible)
    oversize = sum(1 for item in evaluated if item.size_tier == "oversize")
    exempt = sum(1 for item in evaluated if item.exempt_used)
    total_kb = sum(item.size_kb for item in evaluated)
    max_kb = max((item.size_kb for item in evaluated), default=0)
    consecutive_rejects = sum(
        1
        for prev, curr in zip(evaluated, evaluated[1:])
        if not prev.eligible and not curr.eligible
    )
    freeze = consecutive_rejects >= 2

    return {
        "total": total,
        "eligible": eligible,
        "oversize": oversize,
        "total_kb": total_kb,
        "max_kb": max_kb,
        "consecutive_rejects": consecutive_rejects,
        "freeze": freeze,
        "exempt": exempt,
    }


def main() -> None:
    payload: object = json.loads(sys.stdin.read())
    min_range_spec, artifacts = parse_request(payload)
    result = process_release_gate(min_range_spec, artifacts)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
