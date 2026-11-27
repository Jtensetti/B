from __future__ import annotations

from dataclasses import dataclass
import json
import posixpath
import re
import sys
from typing import Literal
from urllib.parse import unquote

SizeTier = Literal["tiny", "standard", "large", "oversize"]

VALID_CHANNELS: frozenset[str] = frozenset({"stable", "beta", "lts"})

NORM_PATH_RE: re.Pattern[str] = re.compile(
    r"[a-z0-9-]+/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?"
)

SEMVER_RE: re.Pattern[str] = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)

CARET_RANGE_RE: re.Pattern[str] = re.compile(
    r"\^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
)


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: str | None = None
    build: str | None = None

    @property
    def core(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)


@dataclass(frozen=True)
class CaretRange:
    lower: tuple[int, int, int]
    upper: tuple[int, int, int]

    def satisfies(self, version: SemVer) -> bool:
        if version.prerelease is not None:
            return False
        return self.lower <= version.core < self.upper


@dataclass(frozen=True)
class ArtifactInput:
    raw_path: str
    channel: str
    size_kb: int


@dataclass(frozen=True)
class GateInput:
    min_range: str
    artifacts: list[ArtifactInput]


@dataclass(frozen=True)
class GateOutput:
    total: int
    eligible: int
    oversize: int
    total_kb: int
    max_kb: int
    consecutive_rejects: int
    freeze: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "eligible": self.eligible,
            "oversize": self.oversize,
            "total_kb": self.total_kb,
            "max_kb": self.max_kb,
            "consecutive_rejects": self.consecutive_rejects,
            "freeze": self.freeze,
        }


def parse_semver(version_str: str) -> SemVer | None:
    match = SEMVER_RE.fullmatch(version_str)
    if match is None:
        return None
    major_s, minor_s, patch_s, prerelease, build = match.groups()
    if prerelease is not None:
        for ident in prerelease.split("."):
            if ident.isdigit() and len(ident) > 1 and ident.startswith("0"):
                return None
    return SemVer(
        major=int(major_s),
        minor=int(minor_s),
        patch=int(patch_s),
        prerelease=prerelease,
        build=build,
    )


def parse_caret_range(range_str: str) -> CaretRange | None:
    match = CARET_RANGE_RE.fullmatch(range_str)
    if match is None:
        return None
    major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
    lower = (major, minor, patch)
    if major > 0:
        upper = (major + 1, 0, 0)
    elif minor > 0:
        upper = (0, minor + 1, 0)
    else:
        upper = (0, 0, patch + 1)
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


def is_eligible(artifact: ArtifactInput, min_range: CaretRange | None) -> bool:
    if classify_size_tier(artifact.size_kb) == "oversize":
        return False
    norm = normalize_artifact_path(artifact.raw_path)
    if NORM_PATH_RE.fullmatch(norm) is None:
        return False
    if artifact.channel not in VALID_CHANNELS:
        return False
    if min_range is None:
        return False

    ver_str = posixpath.basename(norm)
    version = parse_semver(ver_str)
    if version is None:
        return False
    return min_range.satisfies(version)


def evaluate_gate(gate_input: GateInput) -> GateOutput:
    parsed_range = parse_caret_range(gate_input.min_range)
    eligibilities = [is_eligible(art, parsed_range) for art in gate_input.artifacts]
    total = len(gate_input.artifacts)
    eligible = sum(1 for ok in eligibilities if ok)
    oversize = sum(
        1 for art in gate_input.artifacts if classify_size_tier(art.size_kb) == "oversize"
    )
    total_kb = sum(art.size_kb for art in gate_input.artifacts)
    max_kb = max((art.size_kb for art in gate_input.artifacts), default=0)
    consecutive_rejects = sum(
        1
        for prev_ok, curr_ok in zip(eligibilities, eligibilities[1:])
        if not prev_ok and not curr_ok
    )
    freeze = consecutive_rejects >= 2
    return GateOutput(
        total=total,
        eligible=eligible,
        oversize=oversize,
        total_kb=total_kb,
        max_kb=max_kb,
        consecutive_rejects=consecutive_rejects,
        freeze=freeze,
    )


def parse_input(raw_text: str) -> GateInput:
    data: object = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("Expected top-level JSON object")

    min_range = data.get("min_range")
    if not isinstance(min_range, str):
        raise ValueError("Expected string 'min_range'")

    raw_artifacts = data.get("artifacts")
    if not isinstance(raw_artifacts, list):
        raise ValueError("Expected list 'artifacts'")

    artifacts: list[ArtifactInput] = []
    for item in raw_artifacts:
        if not isinstance(item, dict):
            raise ValueError("Expected artifact object")
        raw_path = item.get("raw_path")
        channel = item.get("channel")
        size_kb = item.get("size_kb")
        if not isinstance(raw_path, str):
            raise ValueError("Expected string 'raw_path'")
        if not isinstance(channel, str):
            raise ValueError("Expected string 'channel'")
        if not isinstance(size_kb, int) or isinstance(size_kb, bool):
            raise ValueError("Expected int 'size_kb'")
        artifacts.append(ArtifactInput(raw_path=raw_path, channel=channel, size_kb=size_kb))

    return GateInput(min_range=min_range, artifacts=artifacts)


def main() -> None:
    gate_input = parse_input(sys.stdin.read())
    result = evaluate_gate(gate_input)
    print(json.dumps(result.to_dict()))


if __name__ == "__main__":
    main()
