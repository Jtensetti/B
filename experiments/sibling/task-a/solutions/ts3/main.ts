import { readFileSync } from "node:fs";
import { distance } from "fastest-levenshtein";

// ---- Types ---------------------------------------------------------------

interface Point {
  lat: number;
  lon: number;
}

interface Order {
  id: string;
  product: string;
  country: string;
  lat: number;
  lon: number;
  date: string;
  business: boolean;
  qty?: number; // optional, defaults to 1
  express?: boolean; // optional, defaults to false
}

interface Input {
  depot: Point;
  catalog: Record<string, number>;
  orders: Order[];
  rates: { EUR: number }; // SEK per EUR
}

interface Quote {
  price: number;
  delivery: string;
  currency: "SEK" | "EUR";
}

interface Output {
  quotes: Record<string, Quote>;
  unknown: string[];
}

// ---- Carrier tariff (port of libs/tariff/tariff.go) ----------------------

const ZONES: Record<string, number> = {
  SE: 1, NO: 2, DK: 2, FI: 2, DE: 3, NL: 3, PL: 3, FR: 4, ES: 4, IT: 4,
};
const START: Record<number, number> = { 1: 49, 2: 79, 3: 99, 4: 129 };
const PER_KG: Record<number, number> = { 1: 6.5, 2: 9.0, 3: 11.0, 4: 14.5 };

/** Zone for an ISO country code, or null when the carrier does not serve it. */
function zone(country: string): number | null {
  const z = ZONES[country.trim().toUpperCase()];
  return z === undefined ? null : z;
}

/** Carrier price in SEK excluding VAT; weight is rounded up to the next half kg. */
function basePrice(z: number, weightKg: number): number {
  const billed = Math.ceil(weightKg * 2) / 2;
  return START[z] + PER_KG[z] * billed;
}

// ---- Road distance (port of libs/geo/src/lib.rs) -------------------------

const EARTH_RADIUS_KM = 6371.0;

function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const rad = (d: number) => (d * Math.PI) / 180;
  const p1 = rad(lat1);
  const p2 = rad(lat2);
  const dp = rad(lat2 - lat1);
  const dl = rad(lon2 - lon1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2.0 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a));
}

/** Road distance estimate: great-circle distance times a detour factor of 1.25. */
function roadKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  return distanceKm(lat1, lon1, lat2, lon2) * 1.25;
}

// ---- VAT (port of libs/Tax/Vat.cs) ----------------------------------------

const VAT_STANDARD: Record<string, number> = {
  SE: 0.25, NO: 0.25, DK: 0.25, FI: 0.255, DE: 0.19,
  NL: 0.21, PL: 0.23, FR: 0.2, ES: 0.21, IT: 0.22,
};
const EU = new Set(["SE", "DK", "FI", "DE", "NL", "PL", "FR", "ES", "IT"]);

/** Standard VAT rate; throws for countries without a rate (as the C# library does). */
function vatRate(country: string): number {
  const r = VAT_STANDARD[country.trim().toUpperCase()];
  if (r === undefined) throw new Error("no VAT rate for " + country);
  return r;
}

/** Reverse charge: business customer in another EU country pays no VAT. */
function reverseCharge(country: string, business: boolean): boolean {
  const c = country.trim().toUpperCase();
  return business && c !== "SE" && EU.has(c);
}

// ---- Working days (port of libs/calendar/workdays.py) ---------------------

const HOLIDAYS_2026 = new Set([
  "2026-01-01", "2026-01-06", "2026-04-03", "2026-04-06", "2026-05-01", "2026-05-14",
  "2026-06-06", "2026-06-19", "2026-12-24", "2026-12-25", "2026-12-26", "2026-12-31",
]);

function parseIsoDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d));
}

function formatIsoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function isWorkday(iso: string): boolean {
  const wd = parseIsoDate(iso).getUTCDay(); // 0 = Sunday
  const weekday = wd === 0 ? 6 : wd - 1; // Monday = 0, as in Python
  return weekday < 5 && !HOLIDAYS_2026.has(iso);
}

/** First working day strictly after the given date. */
function nextWorkday(iso: string): string {
  const d = parseIsoDate(iso);
  d.setUTCDate(d.getUTCDate() + 1);
  let s = formatIsoDate(d);
  while (!isWorkday(s)) {
    d.setUTCDate(d.getUTCDate() + 1);
    s = formatIsoDate(d);
  }
  return s;
}

// ---- Product matching ------------------------------------------------------

/**
 * Catalog name with the smallest Levenshtein distance (at most 2); ties go to
 * the alphabetically first name. Returns null when nothing is close enough.
 */
function matchProduct(name: string, catalogNames: string[]): string | null {
  let best: string | null = null;
  let bestDist = Infinity;
  for (const cand of catalogNames) {
    const d = distance(name, cand);
    if (d < bestDist || (d === bestDist && best !== null && cand < best)) {
      best = cand;
      bestDist = d;
    }
  }
  return best !== null && bestDist <= 2 ? best : null;
}

// ---- Quoting ----------------------------------------------------------------

const ROUND_KM = 300;
const EXTRA_PER_KM = 0.8;
const SURCHARGE_CAP_SEK = 400;
const FREE_FREIGHT_KG = 50;

function round2(x: number): number {
  return Math.round((x + Number.EPSILON) * 100) / 100;
}

function quote(input: Input): Output {
  const catalogNames = Object.keys(input.catalog).sort();
  const quotes: Record<string, Quote> = {};
  const unknown: string[] = [];

  for (const o of input.orders) {
    const z = zone(o.country);
    const product = matchProduct(o.product, catalogNames);
    if (z === null || product === null) {
      unknown.push(o.id);
      continue;
    }

    const qty = o.qty ?? 1;
    const weight = qty * input.catalog[product];
    const km = roadKm(input.depot.lat, input.depot.lon, o.lat, o.lon);
    const extraKm = Math.max(0, km - ROUND_KM);
    const express = o.express === true;
    const freeFreight = o.business && weight >= FREE_FREIGHT_KG;
    const basePart = freeFreight ? 0 : basePrice(z, weight);
    const base = basePart * (express ? 1.5 : 1);
    const surcharge = Math.min(EXTRA_PER_KM * extraKm, SURCHARGE_CAP_SEK);
    const net = base + surcharge;
    const vat = reverseCharge(o.country, o.business) ? 0 : vatRate(o.country);
    const priceSek = net * (1 + vat);

    const delivery = express && isWorkday(o.date) ? o.date : nextWorkday(o.date);
    if (o.country.trim().toUpperCase() === "SE") {
      quotes[o.id] = { price: round2(priceSek), delivery, currency: "SEK" };
    } else {
      quotes[o.id] = { price: round2(priceSek / input.rates.EUR), delivery, currency: "EUR" };
    }
  }

  unknown.sort();
  return { quotes, unknown };
}

// ---- Entry point -------------------------------------------------------------

const input: Input = JSON.parse(readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(quote(input)) + "\n");
