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

interface AuditReport {
  count: number;
  breaches: number;
  overage_ms: number;
  max_ms: number;
  mean_ms: number;
  bucket_zero: number;
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
  const payload = JSON.parse(rawInput) as InputPayload;
  const report = auditTelemetry(payload);
  process.stdout.write(`${JSON.stringify(report)}\n`);
}

main();
