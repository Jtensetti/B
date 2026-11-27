from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import json
import sys
from typing import Any


@dataclass(frozen=True)
class Sample:
    service: str
    ms: int
    offset: int


@dataclass(frozen=True)
class AuditInput:
    sla_s: float
    samples: list[Sample]


@dataclass(frozen=True)
class AuditResult:
    count: int
    breaches: int
    overage_ms: int
    max_ms: int
    mean_ms: int
    bucket_zero: int

    def to_dict(self) -> dict[str, int]:
        return {
            "count": self.count,
            "breaches": self.breaches,
            "overage_ms": self.overage_ms,
            "max_ms": self.max_ms,
            "mean_ms": self.mean_ms,
            "bucket_zero": self.bucket_zero,
        }


def normalize_service(name: str) -> str:
    return name.strip().lower()


def rem_euclid(value: int, modulus: int) -> int:
    return value % modulus


def parse_input(raw: dict[str, Any]) -> AuditInput:
    sla_s = float(raw["sla_s"])
    raw_samples: list[dict[str, Any]] = raw["samples"]
    samples = [
        Sample(
            service=normalize_service(str(item["service"])),
            ms=int(item["ms"]),
            offset=int(item["offset"]),
        )
        for item in raw_samples
    ]
    return AuditInput(sla_s=sla_s, samples=samples)


def audit_stream(data: AuditInput) -> AuditResult:
    sla_ms = data.sla_s * 1000.0
    sla_ms_int = round(sla_ms)

    count = len(data.samples)
    if count == 0:
        return AuditResult(
            count=0,
            breaches=0,
            overage_ms=0,
            max_ms=0,
            mean_ms=0,
            bucket_zero=0,
        )

    breaches = 0
    overage_ms = 0
    total_ms = 0
    max_ms = data.samples[0].ms
    bucket_zero = 0

    for sample in data.samples:
        if float(sample.ms) > sla_ms:
            breaches += 1
            overage_ms += sample.ms - sla_ms_int
        total_ms += sample.ms
        if sample.ms > max_ms:
            max_ms = sample.ms
        if rem_euclid(sample.offset, 4) == 0:
            bucket_zero += 1

    mean_ms = round(Fraction(total_ms, count))

    return AuditResult(
        count=count,
        breaches=breaches,
        overage_ms=overage_ms,
        max_ms=max_ms,
        mean_ms=mean_ms,
        bucket_zero=bucket_zero,
    )


def main() -> None:
    payload: dict[str, Any] = json.load(sys.stdin)
    audit_input = parse_input(payload)
    result = audit_stream(audit_input)
    print(json.dumps(result.to_dict()))


if __name__ == "__main__":
    main()
