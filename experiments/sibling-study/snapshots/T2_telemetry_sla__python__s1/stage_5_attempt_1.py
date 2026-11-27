from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import json
import sys
from typing import Any, Literal, TypedDict

Severity = Literal["ok", "warn", "slow", "critical"]
Status = Literal["green", "yellow", "red"]


class AuditResult(TypedDict):
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


@dataclass(frozen=True)
class Sample:
    service: str
    ms: int
    offset: int


@dataclass(frozen=True)
class AuditInput:
    sla_s: float
    samples: list[Sample]


def normalize_service(name: str) -> str:
    return name.strip().lower()


def is_valid_service_label(service: str) -> bool:
    codepoint_count = len(service)
    return 2 <= codepoint_count <= 12


def rem_euclid(value: int, modulus: int) -> int:
    if modulus <= 0:
        raise ValueError("modulus must be positive")
    return value % modulus


def classify_latency(ms: int) -> Severity:
    if ms < 200:
        return "ok"
    if ms <= 500:
        return "warn"
    if ms <= 1000:
        return "slow"
    return "critical"


def determine_status(
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


def parse_input(payload: dict[str, Any]) -> AuditInput:
    sla_s = float(payload["sla_s"])
    raw_samples = payload["samples"]
    samples: list[Sample] = []
    for item in raw_samples:
        samples.append(
            Sample(
                service=normalize_service(str(item["service"])),
                ms=int(item["ms"]),
                offset=int(item["offset"]),
            )
        )
    return AuditInput(sla_s=sla_s, samples=samples)


def audit_stream(audit_input: AuditInput) -> AuditResult:
    sla_ms = audit_input.sla_s * 1000.0
    sla_ms_int = round(sla_ms)

    samples = audit_input.samples
    count = len(samples)
    if count == 0:
        return {
            "count": 0,
            "breaches": 0,
            "overage_ms": 0,
            "max_ms": 0,
            "mean_ms": 0,
            "bucket_zero": 0,
            "critical": 0,
            "warn_or_worse": 0,
            "consecutive_breaches": 0,
            "spike_steps": 0,
            "invalid_labels": 0,
            "exempt": 0,
            "regressed": 0,
            "status": "green",
        }

    breaches = 0
    overage_ms = 0
    valid_total_ms = 0
    valid_count = 0
    invalid_labels = 0
    max_ms = samples[0].ms
    bucket_zero = 0
    critical = 0
    warn_or_worse = 0
    consecutive_breaches = 0
    spike_steps = 0
    exempt = 0
    regressed = 0

    prev_sample: Sample | None = None
    prev_breach = False
    min_seen_ms: int | None = None

    for sample in samples:
        if is_valid_service_label(sample.service):
            valid_total_ms += sample.ms
            valid_count += 1
        else:
            invalid_labels += 1
        if sample.ms > max_ms:
            max_ms = sample.ms
        if min_seen_ms is None:
            min_seen_ms = sample.ms
        else:
            if min_seen_ms + 300 < sample.ms:
                regressed += 1
            if sample.ms < min_seen_ms:
                min_seen_ms = sample.ms
        in_bucket_zero = rem_euclid(sample.offset, 4) == 0
        if in_bucket_zero:
            bucket_zero += 1
        raw_breach = float(sample.ms) > sla_ms
        is_exempt_window = sample.service == "healthcheck" and in_bucket_zero
        if raw_breach and is_exempt_window:
            exempt += 1
            is_breach = False
        else:
            is_breach = raw_breach
        if is_breach:
            breaches += 1
            overage_ms += sample.ms - sla_ms_int
        severity = classify_latency(sample.ms)
        if severity == "critical":
            critical += 1
        if severity != "ok":
            warn_or_worse += 1
        if prev_sample is not None:
            if prev_breach and is_breach:
                consecutive_breaches += 1
            if sample.ms > prev_sample.ms + 100:
                spike_steps += 1
        prev_sample = sample
        prev_breach = is_breach

    mean_ms = round(Fraction(valid_total_ms, valid_count)) if valid_count > 0 else 0
    status = determine_status(consecutive_breaches, critical, breaches, invalid_labels)

    return {
        "count": count,
        "breaches": breaches,
        "overage_ms": overage_ms,
        "max_ms": max_ms,
        "mean_ms": mean_ms,
        "bucket_zero": bucket_zero,
        "critical": critical,
        "warn_or_worse": warn_or_worse,
        "consecutive_breaches": consecutive_breaches,
        "spike_steps": spike_steps,
        "invalid_labels": invalid_labels,
        "exempt": exempt,
        "regressed": regressed,
        "status": status,
    }


def main() -> None:
    raw_data: Any = json.load(sys.stdin)
    if not isinstance(raw_data, dict):
        raise ValueError("Expected a JSON object on stdin")
    audit_input = parse_input(raw_data)
    result = audit_stream(audit_input)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
