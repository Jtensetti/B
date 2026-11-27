import * as fs from "fs";

interface RawSample {
  service: string;
  ms: number;
  offset: number;
}

interface InputPayload {
  sla_s: number;
  samples: RawSample[];
}

interface NormalizedSample {
  service: string;
  ms: number;
  offset: number;
}

type LatencySeverity = "ok" | "warn" | "slow" | "critical";

interface AuditReport {
  count: number;
  breaches: number;
  overage_ms: number;
  max_ms: number;
  mean_ms: number;
  bucket_zero: number;
  critical: number;
  warn_or_worse: number;
  consecutive_breaches: number;
  spike_steps: number;
  invalid_labels: number;
}

function roundHalfToEven(value: number): number {
  const truncated = Math.trunc(value);
  const fraction = Math.abs(value - truncated);
  let rounded: number;

  if (fraction < 0.5) {
    rounded = truncated;
  } else if (fraction > 0.5) {
    rounded = value >= 0 ? truncated + 1 : truncated - 1;
  } else if (truncated % 2 === 0) {
    rounded = truncated;
  } else {
    rounded = value >= 0 ? truncated + 1 : truncated - 1;
  }

  return Object.is(rounded, -0) ? 0 : rounded;
}

function remEuclid(dividend: number, divisor: number): number {
  const remainder = dividend % divisor;
  if (remainder < 0) {
    return remainder + Math.abs(divisor);
  }
  return remainder === 0 ? 0 : remainder;
}

function normalizeService(service: string): string {
  return service.trim().toLowerCase();
}

function isValidServiceLabel(service: string): boolean {
  const codepointCount = Array.from(service).length;
  return codepointCount >= 2 && codepointCount <= 12;
}

function classifySeverity(ms: number): LatencySeverity {
  if (ms < 200) {
    return "ok";
  }
  if (ms <= 500) {
    return "warn";
  }
  if (ms <= 1000) {
    return "slow";
  }
  return "critical";
}

function auditTelemetry(payload: InputPayload): AuditReport {
  const slaMs = payload.sla_s * 1000.0;
  const slaMsInt = roundHalfToEven(slaMs);

  const samples: NormalizedSample[] = payload.samples.map((sample) => ({
    service: normalizeService(sample.service),
    ms: sample.ms,
    offset: sample.offset,
  }));

  const count = samples.length;
  if (count === 0) {
    return {
      count: 0,
      breaches: 0,
      overage_ms: 0,
      max_ms: 0,
      mean_ms: 0,
      bucket_zero: 0,
      critical: 0,
      warn_or_worse: 0,
      consecutive_breaches: 0,
      spike_steps: 0,
      invalid_labels: 0,
    };
  }

  let breaches = 0;
  let overageMs = 0;
  let maxMs = samples[0].ms;
  let validTotalMs = 0;
  let validCount = 0;
  let invalidLabels = 0;
  let bucketZero = 0;
  let critical = 0;
  let warnOrWorse = 0;
  let consecutiveBreaches = 0;
  let spikeSteps = 0;

  let previousSample: NormalizedSample | null = null;

  for (const sample of samples) {
    if (isValidServiceLabel(sample.service)) {
      validTotalMs += sample.ms;
      validCount += 1;
    } else {
      invalidLabels += 1;
    }
    if (sample.ms > maxMs) {
      maxMs = sample.ms;
    }
    const isBreach = sample.ms > slaMs;
    if (isBreach) {
      breaches += 1;
      overageMs += sample.ms - slaMsInt;
    }
    if (remEuclid(sample.offset, 4) === 0) {
      bucketZero += 1;
    }
    const severity = classifySeverity(sample.ms);
    if (severity === "critical") {
      critical += 1;
    }
    if (severity !== "ok") {
      warnOrWorse += 1;
    }
    if (previousSample !== null) {
      if (previousSample.ms > slaMs && isBreach) {
        consecutiveBreaches += 1;
      }
      if (sample.ms > previousSample.ms + 100) {
        spikeSteps += 1;
      }
    }
    previousSample = sample;
  }

  const meanMs = validCount === 0 ? 0 : roundHalfToEven(validTotalMs / validCount);

  return {
    count,
    breaches,
    overage_ms: overageMs,
    max_ms: maxMs,
    mean_ms: meanMs,
    bucket_zero: bucketZero,
    critical,
    warn_or_worse: warnOrWorse,
    consecutive_breaches: consecutiveBreaches,
    spike_steps: spikeSteps,
    invalid_labels: invalidLabels,
  };
}

function main(): void {
  const rawInput = fs.readFileSync(0, "utf8");
  const payload = JSON.parse(rawInput) as InputPayload;
  const report = auditTelemetry(payload);
  process.stdout.write(`${JSON.stringify(report)}\n`);
}

main();
