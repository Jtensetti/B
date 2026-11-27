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

interface QuoteRequest {
  eur_to_sek: number;
  max_sek: number;
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
  vip_exempt: number;
  within_cap: boolean;
  max_leg_eur_cents: number;
}

const DEPOT_PATTERN = /^[a-z]{3}-[0-9]{2}$/;
const VALID_ZONES: ReadonlySet<string> = new Set<Zone>(["SE", "EU", "NON-EU"]);

function isValidZone(zone: string): zone is Zone {
  return VALID_ZONES.has(zone);
}

function roundHalfToEven(value: number): number {
  if (!Number.isFinite(value) || value === 0) {
    return 0;
  }
  const sign = value < 0 ? -1 : 1;
  const absVal = Math.abs(value);
  const floorVal = Math.floor(absVal);
  const diff = absVal - floorVal;
  let rounded: number;
  if (diff < 0.5) {
    rounded = floorVal;
  } else if (diff > 0.5) {
    rounded = floorVal + 1;
  } else {
    rounded = floorVal % 2 === 0 ? floorVal : floorVal + 1;
  }
  const result = sign * rounded;
  return result === 0 ? 0 : result;
}

function normalizeDepot(route: string): string {
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

function computeQuote(request: QuoteRequest): QuoteOutput {
  let validLegs = 0;
  let heavyLegs = 0;
  let customsLegs = 0;
  let longHaulPairs = 0;
  let vipExempt = 0;
  let prevWasLongHaul = false;
  let totalKm = 0.0;
  let totalEur = 0.0;
  let maxLegEurCents = 0;

  for (const leg of request.legs) {
    const depot = normalizeDepot(leg.route);
    const zone = normalizeZone(leg.zone);

    if (!DEPOT_PATTERN.test(depot) || !isValidZone(zone)) {
      continue;
    }

    validLegs += 1;
    const km = Math.sqrt(leg.dx_km * leg.dx_km + leg.dy_km * leg.dy_km);
    const kg = leg.weight_g / 1000.0;
    const baseEur = 5.0 + 0.5 * km + 2.0 * kg;
    let legEur = baseEur * distanceMultiplier(km);
    if (kg >= 10.0) {
      heavyLegs += 1;
      if (depot === "sto-01" && zone === "SE") {
        vipExempt += 1;
      } else {
        legEur += 12.0;
      }
    }
    if (zone === "NON-EU") {
      customsLegs += 1;
    }
    legEur = applyZoneAdjustment(legEur, zone);

    const isLongHaul = km > 100.0;
    if (prevWasLongHaul && isLongHaul) {
      longHaulPairs += 1;
    }
    prevWasLongHaul = isLongHaul;

    totalKm += km;
    totalEur += legEur;

    const legEurCents = roundHalfToEven(legEur * 100.0);
    if (validLegs === 1 || legEurCents > maxLegEurCents) {
      maxLegEurCents = legEurCents;
    }
  }

  totalEur += 25.0 * longHaulPairs;
  const totalSek = roundHalfToEven(totalEur * request.eur_to_sek);

  return {
    legs: request.legs.length,
    valid_legs: validLegs,
    total_m: roundHalfToEven(totalKm * 1000.0),
    total_eur_cents: roundHalfToEven(totalEur * 100.0),
    total_sek: totalSek,
    heavy_legs: heavyLegs,
    customs_legs: customsLegs,
    long_haul_pairs: longHaulPairs,
    vip_exempt: vipExempt,
    within_cap: totalSek <= request.max_sek,
    max_leg_eur_cents: maxLegEurCents,
  };
}

function main(): void {
  const rawInput = fs.readFileSync(0, "utf8");
  const request = JSON.parse(rawInput) as QuoteRequest;
  const output = computeQuote(request);
  process.stdout.write(`${JSON.stringify(output)}\n`);
}

main();
