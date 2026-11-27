import * as fs from "fs";

interface RawSample {
  service: string;
  ms: number;
  offset: number;
}

interface TelemetryInput {
  sla_s: number;
  samples: RawSample[];
}

type Severity = "ok" | "warn" | "slow" | "critical";

interface NormalizedSample {
  service: string;
  ms: number;
  offset: number;
  severity: Severity;
}

interface TelemetryOutput {
  count: number;
  breaches: number;
  overage_ms: number;
  max_ms: number;
  mean_ms: number;
  bucket_zero: number;
  critical: number;
  warn_or_worse: number;
}

function roundHalfToEven(value: number): number {
  if (!Number.isFinite(value)) {
    throw new Error(`Expected finite number, got ${value}`);
  }
  if (Number.isInteger(value)) {
    return value === 0 ? 0 : value;
  }

  const sign = value < 0 ? -1 : 1;
  const absValue = Math.abs(value);
  const floorAbs = Math.floor(absValue);
  const frac = absValue - floorAbs;

  let roundedAbs: number;
  if (frac < 0.5) {
    roundedAbs = floorAbs;
  } else if (frac > 0.5) {
    roundedAbs = floorAbs + 1;
  } else {
    roundedAbs = floorAbs % 2 === 0 ? floorAbs : floorAbs + 1;
  }

  const result = sign * roundedAbs;
  return result === 0 ? 0 : result;
}

function remEuclid(dividend: number, divisor: number): number {
  const remainder = dividend % divisor;
  if (remainder < 0) {
    return remainder + divisor;
  }
  return remainder === 0 ? 0 : remainder;
}

function normalizeService(service: string): string {
  return service.trim().toLowerCase();
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

function auditTelemetry(input: TelemetryInput): TelemetryOutput {
  const slaMs = input.sla_s * 1000.0;
  const slaMsInt = roundHalfToEven(slaMs);

  const samples: NormalizedSample[] = input.samples.map((raw) => ({
    service: normalizeService(raw.service),
    ms: raw.ms,
    offset: raw.offset,
    severity: classifySeverity(raw.ms),
  }));

  const count = samples.length;
  let breaches = 0;
  let overageMs = 0;
  let maxMs = count > 0 ? samples[0].ms : 0;
  let sumMs = 0;
  let bucketZero = 0;
  let critical = 0;
  let warnOrWorse = 0;

  for (const sample of samples) {
    sumMs += sample.ms;
    if (sample.ms > maxMs) {
      maxMs = sample.ms;
    }
    if (sample.ms > slaMs) {
      breaches += 1;
      overageMs += sample.ms - slaMsInt;
    }
    if (remEuclid(sample.offset, 4) === 0) {
      bucketZero += 1;
    }
    if (sample.severity === "critical") {
      critical += 1;
    }
    if (sample.severity !== "ok") {
      warnOrWorse += 1;
    }
  }

  const meanMs = count > 0 ? roundHalfToEven(sumMs / count) : 0;

  return {
    count,
    breaches,
    overage_ms: overageMs,
    max_ms: maxMs,
    mean_ms: meanMs,
    bucket_zero: bucketZero,
    critical,
    warn_or_worse: warnOrWorse,
  };
}

function main(): void {
  const rawInput = fs.readFileSync(0, "utf8");
  const input = JSON.parse(rawInput) as TelemetryInput;
  const output = auditTelemetry(input);
  process.stdout.write(`${JSON.stringify(output)}\n`);
}

main();
