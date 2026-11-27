from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import json
import sys
from typing import Any, Literal

Severity = Literal["ok", "warn", "slow", "critical"]
Status = Literal["green", "yellow", "red"]


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
    critical: int
    warn_or_worse: int
    consecutive_breaches: int
    spike_steps: int
    invalid_labels: int
    exempt: int
    regressed: int
    status: Status

    def to_dict(self) -> dict[str, int | str]:
        return {
            "count": self.count,
            "breaches": self.breaches,
            "overage_ms": self.overage_ms,
            "max_ms": self.max_ms,
            "mean_ms": self.mean_ms,
            "bucket_zero": self.bucket_zero,
            "critical": self.critical,
            "warn_or_worse": self.warn_or_worse,
            "consecutive_breaches": self.consecutive_breaches,
            "spike_steps": self.spike_steps,
            "invalid_labels": self.invalid_labels,
            "exempt": self.exempt,
            "regressed": self.regressed,
            "status": self.status,
        }


def normalize_service(name: str) -> str:
    return name.strip().lower()


def is_valid_service_label(service: str) -> bool:
    return 2 <= len(service) <= 12


def rem_euclid(value: int, modulus: int) -> int:
    return value % modulus


def is_maintenance_exempt(sample: Sample) -> bool:
    return sample.service == "healthcheck" and rem_euclid(sample.offset, 4) == 0


def classify_severity(ms: int) -> Severity:
    if ms < 200:
        return "ok"
    if ms <= 500:
        return "warn"
    if ms <= 1000:
        return "slow"
    return "critical"


def classify_status(
    consecutive_breaches: int,
    critical: int,
    breaches: int,
    invalid_labels: int,
) -> Status:
    if consecutive_breaches >= 2 or critical > 0:
        return "red"
    if breaches > 0 or invalid_labels > 0:
        return "yellow"
    return "green"


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
            critical=0,
            warn_or_worse=0,
            consecutive_breaches=0,
            spike_steps=0,
            invalid_labels=0,
            exempt=0,
            regressed=0,
            status="green",
        )

    breaches = 0
    overage_ms = 0
    valid_total_ms = 0
    valid_count = 0
    invalid_labels = 0
    exempt = 0
    max_ms = data.samples[0].ms
    bucket_zero = 0
    critical = 0
    warn_or_worse = 0
    consecutive_breaches = 0
    spike_steps = 0
    regressed = 0
    prev_ms: int | None = None
    prev_breach = False
    earlier_min_ms: int | None = None

    for sample in data.samples:
        raw_breach = float(sample.ms) > sla_ms
        if raw_breach and is_maintenance_exempt(sample):
            exempt += 1
            is_breach = False
        else:
            is_breach = raw_breach
        if is_breach:
            breaches += 1
            overage_ms += sample.ms - sla_ms_int
        if prev_ms is not None:
            if prev_breach and is_breach:
                consecutive_breaches += 1
            if sample.ms > prev_ms + 100:
                spike_steps += 1
        prev_ms = sample.ms
        prev_breach = is_breach
        if earlier_min_ms is not None:
            if earlier_min_ms + 300 < sample.ms:
                regressed += 1
            if sample.ms < earlier_min_ms:
                earlier_min_ms = sample.ms
        else:
            earlier_min_ms = sample.ms
        if is_valid_service_label(sample.service):
            valid_total_ms += sample.ms
            valid_count += 1
        else:
            invalid_labels += 1
        if sample.ms > max_ms:
            max_ms = sample.ms
        if rem_euclid(sample.offset, 4) == 0:
            bucket_zero += 1
        severity = classify_severity(sample.ms)
        if severity == "critical":
            critical += 1
        if severity != "ok":
            warn_or_worse += 1

    mean_ms = round(Fraction(valid_total_ms, valid_count)) if valid_count > 0 else 0
    status = classify_status(consecutive_breaches, critical, breaches, invalid_labels)

    return AuditResult(
        count=count,
        breaches=breaches,
        overage_ms=overage_ms,
        max_ms=max_ms,
        mean_ms=mean_ms,
        bucket_zero=bucket_zero,
        critical=critical,
        warn_or_worse=warn_or_worse,
        consecutive_breaches=consecutive_breaches,
        spike_steps=spike_steps,
        invalid_labels=invalid_labels,
        exempt=exempt,
        regressed=regressed,
        status=status,
    )


def main() -> None:
    payload: dict[str, Any] = json.load(sys.stdin)
    audit_input = parse_input(payload)
    result = audit_stream(audit_input)
    print(json.dumps(result.to_dict()))


if __name__ == "__main__":
    main()
