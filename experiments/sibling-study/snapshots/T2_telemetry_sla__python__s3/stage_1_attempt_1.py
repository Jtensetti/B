from __future__ import annotations

from dataclasses import dataclass
import json
import sys
from typing import Literal, Mapping


MS_PER_SECOND: float = 1000.0
BUCKET_MODULUS: int = 4
Severity = Literal["ok", "warn", "slow", "critical"]


@dataclass(frozen=True)
class Sample:
    service: str
    ms: int
    offset: int


@dataclass(frozen=True)
class AuditRequest:
    sla_s: float
    samples: list[Sample]


@dataclass(frozen=True)
class AuditReport:
    count: int
    breaches: int
    overage_ms: int
    max_ms: int
    mean_ms: int
    bucket_zero: int
    critical: int
    warn_or_worse: int

    def to_dict(self) -> dict[str, int]:
        return {
            "count": self.count,
            "breaches": self.breaches,
            "overage_ms": self.overage_ms,
            "max_ms": self.max_ms,
            "mean_ms": self.mean_ms,
            "bucket_zero": self.bucket_zero,
            "critical": self.critical,
            "warn_or_worse": self.warn_or_worse,
        }


def classify_latency(ms: int) -> Severity:
    if ms < 200:
        return "ok"
    if ms <= 500:
        return "warn"
    if ms <= 1000:
        return "slow"
    return "critical"


def normalize_service(name: str) -> str:
    return name.strip().lower()


def rem_euclid(value: int, modulus: int) -> int:
    if modulus == 0:
        raise ValueError("modulus must be non-zero")
    abs_mod = abs(modulus)
    return value % abs_mod


def _require_float(raw: object, field: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"Expected numeric value for '{field}'")
    return float(raw)


def _require_int(raw: object, field: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"Expected integer value for '{field}'")
    return raw


def _require_str(raw: object, field: str) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"Expected string value for '{field}'")
    return raw


def parse_sample(raw: object) -> Sample:
    if not isinstance(raw, Mapping):
        raise ValueError("Expected JSON object for sample")
    service = normalize_service(_require_str(raw.get("service"), "service"))
    ms = _require_int(raw.get("ms"), "ms")
    offset = _require_int(raw.get("offset"), "offset")
    return Sample(service=service, ms=ms, offset=offset)


def parse_request(raw: object) -> AuditRequest:
    if not isinstance(raw, Mapping):
        raise ValueError("Expected top-level JSON object")
    sla_s = _require_float(raw.get("sla_s"), "sla_s")
    raw_samples = raw.get("samples")
    if not isinstance(raw_samples, list):
        raise ValueError("Expected list for 'samples'")
    samples = [parse_sample(item) for item in raw_samples]
    return AuditRequest(sla_s=sla_s, samples=samples)


def audit_stream(request: AuditRequest) -> AuditReport:
    sla_ms = request.sla_s * MS_PER_SECOND
    sla_ms_int = round(sla_ms)

    count = len(request.samples)
    if count == 0:
        return AuditReport(
            count=0,
            breaches=0,
            overage_ms=0,
            max_ms=0,
            mean_ms=0,
            bucket_zero=0,
            critical=0,
            warn_or_worse=0,
        )

    breaches = 0
    overage_ms = 0
    total_ms = 0
    max_ms = request.samples[0].ms
    bucket_zero = 0
    critical = 0
    warn_or_worse = 0

    for sample in request.samples:
        total_ms += sample.ms
        if sample.ms > max_ms:
            max_ms = sample.ms
        if float(sample.ms) > sla_ms:
            breaches += 1
            overage_ms += sample.ms - sla_ms_int
        if rem_euclid(sample.offset, BUCKET_MODULUS) == 0:
            bucket_zero += 1
        severity = classify_latency(sample.ms)
        if severity == "critical":
            critical += 1
        if severity != "ok":
            warn_or_worse += 1

    mean_ms = round(total_ms / count)

    return AuditReport(
        count=count,
        breaches=breaches,
        overage_ms=overage_ms,
        max_ms=max_ms,
        mean_ms=mean_ms,
        bucket_zero=bucket_zero,
        critical=critical,
        warn_or_worse=warn_or_worse,
    )


def main() -> None:
    payload: object = json.load(sys.stdin)
    request = parse_request(payload)
    report = audit_stream(request)
    print(json.dumps(report.to_dict()))


if __name__ == "__main__":
    main()
