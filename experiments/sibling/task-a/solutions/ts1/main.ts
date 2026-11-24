// Delivery quotes for a furniture shop in Stockholm.
// Reads one line of JSON from stdin, writes one line of JSON to stdout.
//
// The rules of the libraries in libs/ are ported here (the Go, Rust, C# and
// Python sources are the specification):
//   tariff   -> zoneOf, basePrice
//   geo      -> roadKm (haversine times 1.25)
//   Tax      -> vatRate, reverseCharge
//   calendar -> isWorkday, nextWorkday
// Product matching uses fastest-levenshtein's distance().

import * as fs from 'node:fs';
import { distance } from 'fastest-levenshtein';

interface Depot {
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
  depot: Depot;
  catalog: Record<string, number>;
  orders: Order[];
  rates?: Record<string, number>;
}

interface Quote {
  price: number;
  currency: string;
  delivery: string;
}

interface Output {
  quotes: Record<string, Quote>;
  unknown: string[];
}

// ---- tariff (libs/tariff/tariff.go) ----

const ZONES = new Map<string, number>([
  ['SE', 1], ['NO', 2], ['DK', 2], ['FI', 2], ['DE', 3], ['NL', 3], ['PL', 3],
  ['FR', 4], ['ES', 4], ['IT', 4],
]);
const START = new Map<number, number>([[1, 49], [2, 79], [3, 99], [4, 129]]);
const PER_KG = new Map<number, number>([[1, 6.5], [2, 9.0], [3, 11.0], [4, 14.5]]);

function normCountry(country: string): string {
  return country.trim().toUpperCase();
}

// Returns the zone (1-4), or undefined when the carrier does not serve the country.
function zoneOf(country: string): number | undefined {
  return ZONES.get(normCountry(country));
}

// Carrier price in SEK excluding VAT. Weight is rounded up to the next half kilogram.
function basePrice(zone: number, weightKg: number): number {
  const billed = Math.ceil(weightKg * 2) / 2;
  return (START.get(zone) as number) + (PER_KG.get(zone) as number) * billed;
}

// ---- Tax (libs/Tax/Vat.cs) ----

const VAT_STANDARD = new Map<string, number>([
  ['SE', 0.25], ['NO', 0.25], ['DK', 0.25], ['FI', 0.255], ['DE', 0.19],
  ['NL', 0.21], ['PL', 0.23], ['FR', 0.20], ['ES', 0.21], ['IT', 0.22],
]);
const EU = new Set<string>(['SE', 'DK', 'FI', 'DE', 'NL', 'PL', 'FR', 'ES', 'IT']);

function vatRate(country: string): number {
  const r = VAT_STANDARD.get(normCountry(country));
  if (r === undefined) {
    throw new Error('no VAT rate for ' + country);
  }
  return r;
}

function reverseCharge(country: string, business: boolean): boolean {
  const c = normCountry(country);
  return business && c !== 'SE' && EU.has(c);
}

// ---- geo (libs/geo/src/lib.rs) ----

const EARTH_RADIUS_KM = 6371.0;

function toRadians(deg: number): number {
  return deg * (Math.PI / 180);
}

function distanceKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const p1 = toRadians(lat1);
  const p2 = toRadians(lat2);
  const dp = toRadians(lat2 - lat1);
  const dl = toRadians(lon2 - lon1);
  const s1 = Math.sin(dp / 2);
  const s2 = Math.sin(dl / 2);
  const a = s1 * s1 + Math.cos(p1) * Math.cos(p2) * (s2 * s2);
  return 2.0 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(a));
}

// Road distance estimate: great-circle distance times 1.25.
function roadKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  return distanceKm(lat1, lon1, lat2, lon2) * 1.25;
}

// ---- calendar (libs/calendar/workdays.py) ----

const HOLIDAYS_2026 = new Set<string>([
  '2026-01-01', '2026-01-06', '2026-04-03', '2026-04-06', '2026-05-01', '2026-05-14',
  '2026-06-06', '2026-06-19', '2026-12-24', '2026-12-25', '2026-12-26', '2026-12-31',
]);

function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number);
  const t = new Date(Date.UTC(y as number, (m as number) - 1, (d as number) + days));
  return t.toISOString().slice(0, 10);
}

function isWorkday(iso: string): boolean {
  const [y, m, d] = iso.split('-').map(Number);
  const weekday = new Date(Date.UTC(y as number, (m as number) - 1, d as number)).getUTCDay();
  // Monday to Friday, and not a Swedish public holiday.
  return weekday >= 1 && weekday <= 5 && !HOLIDAYS_2026.has(iso);
}

// First working day strictly after the given date.
function nextWorkday(iso: string): string {
  let d = addDays(iso, 1);
  while (!isWorkday(d)) {
    d = addDays(d, 1);
  }
  return d;
}

// ---- quoting ----

// Rounds to 2 decimals, half up, on the shortest decimal representation.
function round2(x: number): number {
  return Number(Math.round(Number(x + 'e2')) + 'e-2');
}

// Catalog name with the smallest Levenshtein distance (at most 2), ties to the
// alphabetically first name. Undefined when none qualifies.
function matchProduct(product: string, names: string[]): string | undefined {
  let best: string | undefined;
  let bestDist = Infinity;
  for (const name of names) {
    const d = distance(product, name);
    if (d < bestDist) {
      best = name;
      bestDist = d;
    }
  }
  return bestDist <= 2 ? best : undefined;
}

function quote(input: Input): Output {
  const names = Object.keys(input.catalog).sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const quotes: Record<string, Quote> = {};
  const unknown: string[] = [];

  for (const o of input.orders) {
    const name = matchProduct(o.product, names);
    const zone = zoneOf(o.country);
    if (name === undefined || zone === undefined) {
      unknown.push(o.id);
      continue;
    }
    const qty = o.qty === undefined ? 1 : o.qty;
    const weight = (input.catalog[name] as number) * qty;
    const road = roadKm(input.depot.lat, input.depot.lon, o.lat, o.lon);
    const beyond = Math.max(0, road - 300);
    const express = o.express === true;
    // Free freight: business customers with a parcel of 50 kg or more pay no BasePrice.
    const freeFreight = o.business && weight >= 50;
    const base = freeFreight ? 0 : basePrice(zone, weight);
    const surcharge = Math.min(400, 0.8 * beyond);
    const net = (express ? base * 1.5 : base) + surcharge;
    const vat = reverseCharge(o.country, o.business) ? 0 : vatRate(o.country);
    const sekPrice = round2(net * (1 + vat));
    // Orders to countries other than Sweden are quoted in EUR (SEK per EUR rate).
    const foreign = normCountry(o.country) !== 'SE';
    const price = foreign ? round2(sekPrice / (input.rates?.EUR as number)) : sekPrice;
    const currency = foreign ? 'EUR' : 'SEK';
    const delivery = express && isWorkday(o.date) ? o.date : nextWorkday(o.date);
    quotes[o.id] = { price, currency, delivery };
  }

  unknown.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  return { quotes, unknown };
}

const raw = fs.readFileSync(0, 'utf8');
const input = JSON.parse(raw) as Input;
process.stdout.write(JSON.stringify(quote(input)) + '\n');
