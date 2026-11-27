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

interface AuditOutput {
  count: number;
  breaches: number;
  overage_ms: number;
  max_ms: number;
  mean_ms: number;
  bucket_zero: number;
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
    };
  }

  let breaches = 0;
  let overageMs = 0;
  let maxMs = samples[0].ms;
  let totalMs = 0;
  let bucketZero = 0;

  for (const sample of samples) {
    totalMs += sample.ms;
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
  }

  const meanMs = roundHalfToEven(totalMs / count);

  return {
    count,
    breaches,
    overage_ms: overageMs,
    max_ms: maxMs,
    mean_ms: meanMs,
    bucket_zero: bucketZero,
  };
}

function main(): void {
  const rawInput = fs.readFileSync(0, "utf8");
  const parsed: AuditInput = JSON.parse(rawInput) as AuditInput;
  const output = auditTelemetry(parsed);
  process.stdout.write(JSON.stringify(output) + "\n");
}

main();
