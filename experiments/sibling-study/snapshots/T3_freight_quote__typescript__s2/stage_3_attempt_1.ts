import * as fs from "fs";
import * as path from "path";

type Zone = "SE" | "EU" | "NON-EU";

interface LegInput {
  route: string;
  dx_km: number;
  dy_km: number;
  weight_g: number;
  zone: string;
}

interface QuoteInput {
  eur_to_sek: number;
  legs: LegInput[];
}

interface QuoteOutput {
  legs: number;
  valid_legs: number;
  total_m: number;
  total_eur_cents: number;
  total_sek: number;
  heavy_legs: number;
  customs_legs: number;
  long_haul_pairs: number;
}

const DEPOT_PATTERN = /^[a-z]{3}-[0-9]{2}$/;
const VALID_ZONES: ReadonlySet<string> = new Set<Zone>(["SE", "EU", "NON-EU"]);

function isValidZone(zone: string): zone is Zone {
  return VALID_ZONES.has(zone);
}

function roundHalfToEven(value: number): number {
  if (!Number.isFinite(value)) {
    return value;
  }
  const floor = Math.floor(value);
  const diff = value - floor;
  let result: number;
  if (diff < 0.5) {
    result = floor;
  } else if (diff > 0.5) {
    result = floor + 1;
  } else {
    result = floor % 2 === 0 ? floor : floor + 1;
  }
  return result === 0 ? 0 : result;
}

function parseDepot(route: string): string {
  const normalized = path.posix.normalize(route);
  return path.posix.basename(normalized);
}

function normalizeZone(zone: string): string {
  return zone.trim().toUpperCase();
}

function distanceMultiplier(km: number): number {
  if (km <= 50.0) {
    return 1.0;
  }
  if (km <= 200.0) {
    return 1.15;
  }
  return 1.35;
}

function applyZoneAdjustment(feeEur: number, zone: Zone): number {
  switch (zone) {
    case "SE":
      return feeEur * 0.9;
    case "EU":
      return feeEur;
    case "NON-EU":
      return feeEur + 15.0;
  }
}

function computeQuote(input: QuoteInput): QuoteOutput {
  let validLegs = 0;
  let heavyLegs = 0;
  let customsLegs = 0;
  let longHaulPairs = 0;
  let prevWasLongHaul = false;
  let totalKm = 0;
  let totalEur = 0;

  for (const leg of input.legs) {
    const depot = parseDepot(leg.route);
    const zone = normalizeZone(leg.zone);

    if (!DEPOT_PATTERN.test(depot) || !isValidZone(zone)) {
      continue;
    }

    validLegs += 1;
    const km = Math.sqrt(leg.dx_km * leg.dx_km + leg.dy_km * leg.dy_km);
    const kg = leg.weight_g / 1000.0;
    const baseEur = 5.0 + 0.5 * km + 2.0 * kg;
    const isHeavy = kg >= 10.0;
    if (isHeavy) {
      heavyLegs += 1;
    }
    if (zone === "NON-EU") {
      customsLegs += 1;
    }
    const isLongHaul = km > 100.0;
    if (prevWasLongHaul && isLongHaul) {
      longHaulPairs += 1;
    }
    prevWasLongHaul = isLongHaul;

    const subtotalEur = baseEur * distanceMultiplier(km) + (isHeavy ? 12.0 : 0.0);
    const legEur = applyZoneAdjustment(subtotalEur, zone);

    totalKm += km;
    totalEur += legEur;
  }

  totalEur += 25.0 * longHaulPairs;

  return {
    legs: input.legs.length,
    valid_legs: validLegs,
    total_m: roundHalfToEven(totalKm * 1000.0),
    total_eur_cents: roundHalfToEven(totalEur * 100.0),
    total_sek: roundHalfToEven(totalEur * input.eur_to_sek),
    heavy_legs: heavyLegs,
    customs_legs: customsLegs,
    long_haul_pairs: longHaulPairs,
  };
}

function main(): void {
  const rawInput = fs.readFileSync(0, "utf8");
  const input = JSON.parse(rawInput) as QuoteInput;
  const output = computeQuote(input);
  process.stdout.write(`${JSON.stringify(output)}\n`);
}

main();
