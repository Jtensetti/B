from __future__ import annotations

from dataclasses import dataclass
import json
import sys
from typing import Any, Literal

Severity = Literal["ok", "warn", "slow", "critical"]


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


def audit_stream(audit_input: AuditInput) -> dict[str, int]:
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
        }

    breaches = 0
    overage_ms = 0
    total_ms = 0
    max_ms = samples[0].ms
    bucket_zero = 0
    critical = 0
    warn_or_worse = 0
    consecutive_breaches = 0
    spike_steps = 0

    prev_sample: Sample | None = None
    prev_breach = False

    for sample in samples:
        total_ms += sample.ms
        if sample.ms > max_ms:
            max_ms = sample.ms
        is_breach = float(sample.ms) > sla_ms
        if is_breach:
            breaches += 1
            overage_ms += sample.ms - sla_ms_int
        if rem_euclid(sample.offset, 4) == 0:
            bucket_zero += 1
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

    mean_ms = round(total_ms / count)

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
