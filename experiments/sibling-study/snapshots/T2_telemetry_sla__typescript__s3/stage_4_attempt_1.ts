import * as fs from "fs";

interface RawSample {
  service: string;
  ms: number;
  offset: number;
}

interface AuditInput {
  sla_s: number;
  samples: RawSample[];
}

interface NormalizedSample {
  service: string;
  ms: number;
  offset: number;
}

type Severity = "ok" | "warn" | "slow" | "critical";

interface AuditOutput {
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
  exempt: number;
}

function roundHalfToEven(value: number): number {
  const sign = value < 0 ? -1 : 1;
  const absValue = Math.abs(value);
  const floor = Math.floor(absValue);
  const frac = absValue - floor;

  let roundedAbs: number;
  if (frac < 0.5) {
    roundedAbs = floor;
  } else if (frac > 0.5) {
    roundedAbs = floor + 1;
  } else {
    roundedAbs = floor % 2 === 0 ? floor : floor + 1;
  }

  const result = sign * roundedAbs;
  return result === 0 ? 0 : result;
}

function remEuclid(value: number, modulus: number): number {
  const m = Math.abs(modulus);
  return ((value % m) + m) % m;
}

function normalizeService(service: string): string {
  return service.trim().toLowerCase();
}

function normalizeSample(raw: RawSample): NormalizedSample {
  return {
    service: normalizeService(raw.service),
    ms: raw.ms,
    offset: raw.offset,
  };
}

function classifySeverity(ms: number): Severity {
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

function codepointCount(text: string): number {
  return Array.from(text).length;
}

function isValidServiceLabel(service: string): boolean {
  const length = codepointCount(service);
  return length >= 2 && length <= 12;
}

function isMaintenanceExempt(sample: NormalizedSample): boolean {
  return sample.service === "healthcheck" && remEuclid(sample.offset, 4) === 0;
}

function auditTelemetry(input: AuditInput): AuditOutput {
  const slaMs = input.sla_s * 1000.0;
  const slaMsInt = roundHalfToEven(slaMs);
  const samples = input.samples.map(normalizeSample);

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
      exempt: 0,
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
  let exempt = 0;
  let previous: NormalizedSample | undefined;
  let previousBreached = false;

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
    const rawBreach = sample.ms > slaMs;
    const isExempt = isMaintenanceExempt(sample);
    const isBreach = rawBreach && !isExempt;
    if (rawBreach && isExempt) {
      exempt += 1;
    } else if (isBreach) {
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
    if (previous !== undefined) {
      if (previousBreached && isBreach) {
        consecutiveBreaches += 1;
      }
      if (sample.ms > previous.ms + 100) {
        spikeSteps += 1;
      }
    }
    previous = sample;
    previousBreached = isBreach;
  }

  const meanMs = validCount > 0 ? roundHalfToEven(validTotalMs / validCount) : 0;

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
    exempt,
  };
}

function main(): void {
  const rawInput = fs.readFileSync(0, "utf8");
  const parsed: AuditInput = JSON.parse(rawInput) as AuditInput;
  const output = auditTelemetry(parsed);
  process.stdout.write(JSON.stringify(output) + "\n");
}

main();
