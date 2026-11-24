// Delivery quotes for a furniture shop in Stockholm.
// Ports of the libs/ modules (tariff, geo, Tax, calendar) plus fastest-levenshtein.

import { readFileSync } from "node:fs";
import { distance } from "fastest-levenshtein";

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
  qty?: number;
  express?: boolean;
}

interface Input {
  depot: Point;
  catalog: Record<string, number>;
  orders: Order[];
  rates?: { EUR: number };
}

interface Quote {
  price: number;
  delivery: string;
  currency: string;
}

// ---- libs/tariff/tariff.go ----

const TARIFF_ZONES: Record<string, number> = {
  SE: 1, NO: 2, DK: 2, FI: 2, DE: 3, NL: 3, PL: 3, FR: 4, ES: 4, IT: 4,
};
const TARIFF_START: Record<number, number> = { 1: 49, 2: 79, 3: 99, 4: 129 };
const TARIFF_PER_KG: Record<number, number> = { 1: 6.5, 2: 9.0, 3: 11.0, 4: 14.5 };

function normCountry(country: string): string {
  return country.trim().toUpperCase();
}

// Returns the zone, or null when the carrier does not serve the country.
function zone(country: string): number | null {
  const c = normCountry(country);
  return Object.prototype.hasOwnProperty.call(TARIFF_ZONES, c) ? TARIFF_ZONES[c] : null;
}

// Carrier price in SEK excluding VAT; weight is rounded up to the next half kilogram.
function basePrice(z: number, weightKg: number): number {
  const billed = Math.ceil(weightKg * 2) / 2;
  return TARIFF_START[z] + TARIFF_PER_KG[z] * billed;
}

// ---- libs/geo/src/lib.rs ----

const EARTH_RADIUS_KM = 6371.0;

function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (d: number): number => (d * Math.PI) / 180;
  const p1 = toRad(lat1);
  const p2 = toRad(lat2);
  const dp = toRad(lat2 - lat1);
  const dl = toRad(lon2 - lon1);
  const a = Math.pow(Math.sin(dp / 2), 2) + Math.cos(p1) * Math.cos(p2) * Math.pow(Math.sin(dl / 2), 2);
  return 2.0 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a));
}

// Road distance estimate: great-circle distance times a detour factor of 1.25.
function roadKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  return distanceKm(lat1, lon1, lat2, lon2) * 1.25;
}

// ---- libs/Tax/Vat.cs ----

const VAT_STANDARD: Record<string, number> = {
  SE: 0.25, NO: 0.25, DK: 0.25, FI: 0.255, DE: 0.19,
  NL: 0.21, PL: 0.23, FR: 0.2, ES: 0.21, IT: 0.22,
};
const VAT_EU: Record<string, boolean> = {
  SE: true, DK: true, FI: true, DE: true, NL: true, PL: true, FR: true, ES: true, IT: true,
};

// Standard VAT rate. Callers only pass countries already known to the tariff.
function vatRate(country: string): number {
  const c = normCountry(country);
  if (!Object.prototype.hasOwnProperty.call(VAT_STANDARD, c)) {
    throw new Error("no VAT rate for " + country);
  }
  return VAT_STANDARD[c];
}

// True when a business customer in another EU country pays no VAT (reverse charge).
function reverseCharge(country: string, business: boolean): boolean {
  const c = normCountry(country);
  return business && c !== "SE" && Object.prototype.hasOwnProperty.call(VAT_EU, c);
}

// ---- libs/calendar/workdays.py ----

const HOLIDAYS_2026: Record<string, boolean> = {
  "2026-01-01": true, "2026-01-06": true, "2026-04-03": true, "2026-04-06": true,
  "2026-05-01": true, "2026-05-14": true, "2026-06-06": true, "2026-06-19": true,
  "2026-12-24": true, "2026-12-25": true, "2026-12-26": true, "2026-12-31": true,
};

function parseIsoUtc(iso: string): Date {
  return new Date(iso + "T00:00:00Z");
}

function isWorkday(iso: string): boolean {
  const weekday = parseIsoUtc(iso).getUTCDay(); // 0 = Sunday
  const monToFri = weekday >= 1 && weekday <= 5;
  return monToFri && !Object.prototype.hasOwnProperty.call(HOLIDAYS_2026, iso);
}

// First working day strictly after the given date.
function nextWorkday(iso: string): string {
  const d = parseIsoUtc(iso);
  d.setUTCDate(d.getUTCDate() + 1);
  let s = d.toISOString().slice(0, 10);
  while (!isWorkday(s)) {
    d.setUTCDate(d.getUTCDate() + 1);
    s = d.toISOString().slice(0, 10);
  }
  return s;
}

// ---- quoting rules ----

// Catalog name with the smallest Levenshtein distance (ties: alphabetically first), if at most 2.
function resolveProduct(name: string, sortedCatalog: string[]): string | null {
  let best: string | null = null;
  let bestD = Infinity;
  for (const cand of sortedCatalog) {
    const d = distance(name, cand);
    if (d < bestD) {
      bestD = d;
      best = cand;
    }
  }
  return best !== null && bestD <= 2 ? best : null;
}

// Round half away from zero to 2 decimals.
function round2(x: number): number {
  return Math.round(x * 100) / 100;
}

function quoteOrder(input: Input, sortedCatalog: string[], o: Order): Quote | null {
  const product = resolveProduct(o.product, sortedCatalog);
  if (product === null) return null;

  const z = zone(o.country);
  if (z === null) return null;

  const road = roadKm(input.depot.lat, input.depot.lon, o.lat, o.lon);
  const extraKm = Math.max(0, road - 300);
  const qty = o.qty ?? 1;
  const weight = qty * input.catalog[product];
  // Free freight: business customers with a parcel of 50 kg or more pay no BasePrice.
  const base = o.business === true && weight >= 50 ? 0 : basePrice(z, weight);
  const surcharge = Math.min(0.8 * extraKm, 400);
  const net = (o.express === true ? base * 1.5 : base) + surcharge;

  const vat = reverseCharge(o.country, o.business) ? 0 : vatRate(o.country);
  const price = round2(net * (1 + vat));

  const delivery = o.express === true && isWorkday(o.date) ? o.date : nextWorkday(o.date);
  if (normCountry(o.country) === "SE") {
    return { price, delivery, currency: "SEK" };
  }
  // Non-Swedish customers pay in euros: the rounded SEK price divided by SEK per EUR.
  const eur = round2(price / input.rates!.EUR);
  return { price: eur, delivery, currency: "EUR" };
}

function main(): void {
  const input = JSON.parse(readFileSync(0, "utf8")) as Input;
  const sortedCatalog = Object.keys(input.catalog).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));

  const quotes: Record<string, Quote> = {};
  const unknown: string[] = [];

  for (const o of input.orders) {
    const q = quoteOrder(input, sortedCatalog, o);
    if (q === null) {
      unknown.push(o.id);
    } else {
      quotes[o.id] = q;
    }
  }

  unknown.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  process.stdout.write(JSON.stringify({ quotes, unknown }) + "\n");
}

main();
