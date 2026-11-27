from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import json
import sys
from typing import Literal, Mapping, Optional, Union


MS_PER_SECOND: float = 1000.0
BUCKET_MODULUS: int = 4
SPIKE_THRESHOLD_MS: int = 100
REGRESSION_THRESHOLD_MS: int = 300
MIN_LABEL_CODEPOINTS: int = 2
MAX_LABEL_CODEPOINTS: int = 12
EXEMPT_SERVICE: str = "healthcheck"
Severity = Literal["ok", "warn", "slow", "critical"]
Status = Literal["red", "yellow", "green"]


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
    consecutive_breaches: int
    spike_steps: int
    invalid_labels: int
    exempt: int
    regressed: int
    status: Status

    def to_dict(self) -> dict[str, Union[int, str]]:
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


def is_breach(ms: int, sla_ms: float) -> bool:
    return float(ms) > sla_ms


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


def is_valid_service_label(service: str) -> bool:
    return MIN_LABEL_CODEPOINTS <= len(service) <= MAX_LABEL_CODEPOINTS


def rem_euclid(value: int, modulus: int) -> int:
    if modulus == 0:
        raise ValueError("modulus must be non-zero")
    abs_mod = abs(modulus)
    return value % abs_mod


def is_maintenance_exempt(sample: Sample) -> bool:
    return sample.service == EXEMPT_SERVICE and rem_euclid(sample.offset, BUCKET_MODULUS) == 0


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
    max_ms = request.samples[0].ms
    min_ms_so_far: Optional[int] = None
    bucket_zero = 0
    critical = 0
    warn_or_worse = 0
    consecutive_breaches = 0
    spike_steps = 0
    regressed = 0
    prev_sample: Optional[Sample] = None
    prev_breached = False

    for sample in request.samples:
        if is_valid_service_label(sample.service):
            valid_total_ms += sample.ms
            valid_count += 1
        else:
            invalid_labels += 1
        if sample.ms > max_ms:
            max_ms = sample.ms
        raw_breached = is_breach(sample.ms, sla_ms)
        if raw_breached and is_maintenance_exempt(sample):
            exempt += 1
            breached = False
        else:
            breached = raw_breached
        if breached:
            breaches += 1
            overage_ms += sample.ms - sla_ms_int
        if rem_euclid(sample.offset, BUCKET_MODULUS) == 0:
            bucket_zero += 1
        severity = classify_latency(sample.ms)
        if severity == "critical":
            critical += 1
        if severity != "ok":
            warn_or_worse += 1
        if prev_sample is not None:
            if prev_breached and breached:
                consecutive_breaches += 1
            if sample.ms > prev_sample.ms + SPIKE_THRESHOLD_MS:
                spike_steps += 1
        if min_ms_so_far is not None:
            if min_ms_so_far + REGRESSION_THRESHOLD_MS < sample.ms:
                regressed += 1
            if sample.ms < min_ms_so_far:
                min_ms_so_far = sample.ms
        else:
            min_ms_so_far = sample.ms
        prev_sample = sample
        prev_breached = breached

    mean_ms = round(Fraction(valid_total_ms, valid_count)) if valid_count > 0 else 0
    status = determine_status(
        consecutive_breaches=consecutive_breaches,
        critical=critical,
        breaches=breaches,
        invalid_labels=invalid_labels,
    )

    return AuditReport(
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
    payload: object = json.load(sys.stdin)
    request = parse_request(payload)
    report = audit_stream(request)
    print(json.dumps(report.to_dict()))


if __name__ == "__main__":
    main()
