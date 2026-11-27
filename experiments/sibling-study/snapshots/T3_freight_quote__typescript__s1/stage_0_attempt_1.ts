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
}

const DEPOT_REGEX = /^[a-z]{3}-[0-9]{2}$/;
const VALID_ZONES: ReadonlySet<string> = new Set<Zone>(["SE", "EU", "NON-EU"]);

function parseZone(raw: string): Zone | null {
  const normalized = raw.trim().toUpperCase();
  if (VALID_ZONES.has(normalized)) {
    return normalized as Zone;
  }
  return null;
}

function extractDepot(route: string): string {
  const normalized = path.posix.normalize(route);
  return path.posix.basename(normalized);
}

function roundHalfToEven(value: number): number {
  const sign = value < 0 ? -1 : 1;
  const abs = Math.abs(value);
  const floorVal = Math.floor(abs);
  const diff = abs - floorVal;

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

function computeQuote(input: QuoteInput): QuoteOutput {
  let validLegs = 0;
  let totalKm = 0;
  let totalEur = 0;

  for (const leg of input.legs) {
    const depot = extractDepot(leg.route);
    const zone = parseZone(leg.zone);

    if (!DEPOT_REGEX.test(depot) || zone === null) {
      continue;
    }

    validLegs += 1;
    const km = Math.sqrt(leg.dx_km * leg.dx_km + leg.dy_km * leg.dy_km);
    const kg = leg.weight_g / 1000.0;
    const legEur = 5.0 + 0.5 * km + 2.0 * kg;

    totalKm += km;
    totalEur += legEur;
  }

  return {
    legs: input.legs.length,
    valid_legs: validLegs,
    total_m: roundHalfToEven(totalKm * 1000.0),
    total_eur_cents: roundHalfToEven(totalEur * 100.0),
    total_sek: roundHalfToEven(totalEur * input.eur_to_sek),
  };
}

function main(): void {
  const raw = fs.readFileSync(0, "utf8");
  const input = JSON.parse(raw) as QuoteInput;
  const output = computeQuote(input);
  process.stdout.write(JSON.stringify(output) + "\n");
}

main();
