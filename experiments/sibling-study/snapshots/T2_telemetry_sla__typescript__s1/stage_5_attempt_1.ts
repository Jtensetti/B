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
type Status = "green" | "yellow" | "red";

interface NormalizedSample {
  service: string;
  ms: number;
  offset: number;
  severity: Severity;
  validLabel: boolean;
  bucketZero: boolean;
  exemptFromBreach: boolean;
  breached: boolean;
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
  consecutive_breaches: number;
  spike_steps: number;
  invalid_labels: number;
  exempt: number;
  regressed: number;
  status: Status;
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

function isValidServiceLabel(service: string): boolean {
  const codepointCount = Array.from(service).length;
  return codepointCount >= 2 && codepointCount <= 12;
}

function isMaintenanceExempt(service: string, bucketZero: boolean): boolean {
  return service === "healthcheck" && bucketZero;
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

function determineStatus(
  consecutiveBreaches: number,
  critical: number,
  breaches: number,
  invalidLabels: number,
): Status {
  if (consecutiveBreaches >= 2 || critical > 0) {
    return "red";
  }
  if (breaches > 0 || invalidLabels > 0) {
    return "yellow";
  }
  return "green";
}

function auditTelemetry(input: TelemetryInput): TelemetryOutput {
  const slaMs = input.sla_s * 1000.0;
  const slaMsInt = roundHalfToEven(slaMs);

  const samples: NormalizedSample[] = input.samples.map((raw) => {
    const service = normalizeService(raw.service);
    const isBucketZero = remEuclid(raw.offset, 4) === 0;
    const rawExceedsSla = raw.ms > slaMs;
    const exemptFromBreach = rawExceedsSla && isMaintenanceExempt(service, isBucketZero);
    const breached = rawExceedsSla && !exemptFromBreach;
    return {
      service,
      ms: raw.ms,
      offset: raw.offset,
      severity: classifySeverity(raw.ms),
      validLabel: isValidServiceLabel(service),
      bucketZero: isBucketZero,
      exemptFromBreach,
      breached,
    };
  });

  const count = samples.length;
  let breaches = 0;
  let overageMs = 0;
  let maxMs = count > 0 ? samples[0].ms : 0;
  let minEarlierMs = count > 0 ? samples[0].ms : 0;
  let validSumMs = 0;
  let validCount = 0;
  let invalidLabels = 0;
  let bucketZero = 0;
  let critical = 0;
  let warnOrWorse = 0;
  let consecutiveBreaches = 0;
  let spikeSteps = 0;
  let exempt = 0;
  let regressed = 0;

  for (let i = 0; i < count; i += 1) {
    const sample = samples[i];
    if (sample.validLabel) {
      validSumMs += sample.ms;
      validCount += 1;
    } else {
      invalidLabels += 1;
    }
    if (sample.ms > maxMs) {
      maxMs = sample.ms;
    }
    if (sample.exemptFromBreach) {
      exempt += 1;
    }
    if (sample.breached) {
      breaches += 1;
      overageMs += sample.ms - slaMsInt;
    }
    if (sample.bucketZero) {
      bucketZero += 1;
    }
    if (sample.severity === "critical") {
      critical += 1;
    }
    if (sample.severity !== "ok") {
      warnOrWorse += 1;
    }
    if (i > 0) {
      const past = samples[i - 1];
      if (past.breached && sample.breached) {
        consecutiveBreaches += 1;
      }
      if (sample.ms > past.ms + 100) {
        spikeSteps += 1;
      }
      if (minEarlierMs + 300 < sample.ms) {
        regressed += 1;
      }
      if (sample.ms < minEarlierMs) {
        minEarlierMs = sample.ms;
      }
    }
  }

  const meanMs = validCount > 0 ? roundHalfToEven(validSumMs / validCount) : 0;
  const status = determineStatus(consecutiveBreaches, critical, breaches, invalidLabels);

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
    regressed,
    status,
  };
}

function main(): void {
  const rawInput = fs.readFileSync(0, "utf8");
  const input = JSON.parse(rawInput) as TelemetryInput;
  const output = auditTelemetry(input);
  process.stdout.write(`${JSON.stringify(output)}\n`);
}

main();
