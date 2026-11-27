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
KB_PER_MB: float = 1024.0

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
    budget_mb: float
    artifacts: list[ArtifactInput]


@dataclass(frozen=True)
class ArtifactEvaluation:
    norm_path: str
    pkg: str
    ver_str: str
    version: SemVer | None
    size_kb: int
    size_tier: SizeTier
    eligible: bool
    exempt: bool


@dataclass(frozen=True)
class GateOutput:
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

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "eligible": self.eligible,
            "oversize": self.oversize,
            "total_kb": self.total_kb,
            "max_kb": self.max_kb,
            "consecutive_rejects": self.consecutive_rejects,
            "freeze": self.freeze,
            "exempt": self.exempt,
            "eligible_kb": self.eligible_kb,
            "within_budget": self.within_budget,
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


def evaluate_artifact(
    artifact: ArtifactInput, min_range: CaretRange | None
) -> ArtifactEvaluation:
    norm = normalize_artifact_path(artifact.raw_path)
    pkg = posixpath.dirname(norm)
    ver_str = posixpath.basename(norm)
    size_tier = classify_size_tier(artifact.size_kb)

    valid_format = (
        NORM_PATH_RE.fullmatch(norm) is not None and artifact.channel in VALID_CHANNELS
    )
    version = parse_semver(ver_str) if valid_format else None

    if not valid_format or version is None or size_tier == "oversize":
        return ArtifactEvaluation(
            norm_path=norm,
            pkg=pkg,
            ver_str=ver_str,
            version=version,
            size_kb=artifact.size_kb,
            size_tier=size_tier,
            eligible=False,
            exempt=False,
        )

    satisfies_range = min_range is not None and min_range.satisfies(version)
    is_lts_security_exempt = (
        artifact.channel == "lts"
        and "security" in pkg
        and version.prerelease is None
        and "-" not in ver_str
    )

    exempt_only = is_lts_security_exempt and not satisfies_range
    eligible = satisfies_range or is_lts_security_exempt
    return ArtifactEvaluation(
        norm_path=norm,
        pkg=pkg,
        ver_str=ver_str,
        version=version,
        size_kb=artifact.size_kb,
        size_tier=size_tier,
        eligible=eligible,
        exempt=exempt_only,
    )


def evaluate_gate(gate_input: GateInput) -> GateOutput:
    parsed_range = parse_caret_range(gate_input.min_range)
    evaluations = [evaluate_artifact(art, parsed_range) for art in gate_input.artifacts]
    total = len(gate_input.artifacts)
    eligible = sum(1 for ev in evaluations if ev.eligible)
    oversize = sum(1 for ev in evaluations if ev.size_tier == "oversize")
    exempt = sum(1 for ev in evaluations if ev.exempt)
    total_kb = sum(ev.size_kb for ev in evaluations)
    max_kb = max((ev.size_kb for ev in evaluations), default=0)
    eligible_kb = sum(ev.size_kb for ev in evaluations if ev.eligible)
    within_budget = eligible_kb <= gate_input.budget_mb * KB_PER_MB
    consecutive_rejects = sum(
        1
        for prev_ev, curr_ev in zip(evaluations, evaluations[1:])
        if not prev_ev.eligible and not curr_ev.eligible
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
        exempt=exempt,
        eligible_kb=eligible_kb,
        within_budget=within_budget,
    )


def parse_input(raw_text: str) -> GateInput:
    data: object = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("Expected top-level JSON object")

    min_range = data.get("min_range")
    if not isinstance(min_range, str):
        raise ValueError("Expected string 'min_range'")

    budget_mb = data.get("budget_mb")
    if not isinstance(budget_mb, (int, float)) or isinstance(budget_mb, bool):
        raise ValueError("Expected number 'budget_mb'")

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

    return GateInput(min_range=min_range, budget_mb=float(budget_mb), artifacts=artifacts)


def main() -> None:
    gate_input = parse_input(sys.stdin.read())
    result = evaluate_gate(gate_input)
    print(json.dumps(result.to_dict()))


if __name__ == "__main__":
    main()
