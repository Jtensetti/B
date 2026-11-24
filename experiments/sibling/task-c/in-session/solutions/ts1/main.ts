// Reorder suggestions for a furniture warehouse.
// Ports of the behaviour of the team libraries in libs/:
//   leadtime (Go)   -> leadDays
//   stats (Rust)    -> mean, percentile
//   Packaging (C#)  -> roundUp
//   weeks (Python)  -> addDays

import * as fs from 'node:fs';
import { distance } from 'fastest-levenshtein';

interface Item {
  sku: string;
  supplier: string;
  stock: number;
  pack: number;
  price: number; // SEK per unit
}

interface Sale {
  sku: string;
  date: string;
  qty: number;
}

interface Input {
  today: string;
  items: Item[];
  sales: Sale[];
}

interface Order {
  qty: number;
  arrive: string;
}

interface Output {
  orders: Record<string, Order>;
  unknown: string[];
}

const WINDOW = 28;
const TRAILING_WINDOW = 7;
const DAY_MS = 86400000;

// leadtime.Days: delivery time in days, or undefined for an unknown supplier.
const LEAD_DAYS = new Map<string, number>([
  ['Nordic Timber', 12],
  ['Baltic Steel', 9],
  ['Lumo Lighting', 5],
  ['Fabrikk AS', 7],
  ['Textil Partner', 14],
]);

// leadtime.Suppliers: the names the lead-time table knows.
const SUPPLIERS: string[] = ['Baltic Steel', 'Fabrikk AS', 'Lumo Lighting', 'Nordic Timber', 'Textil Partner'];
const MAX_SUPPLIER_DISTANCE = 2;
const MIN_ORDER_SEK = 500;

// Closest known supplier name within distance 2 (ties: alphabetically first), else undefined.
function resolveSupplier(name: string): string | undefined {
  let best: string | undefined;
  let bestDist = Infinity;
  for (const candidate of [...SUPPLIERS].sort(compareStrings)) {
    const d = distance(name, candidate);
    if (d < bestDist) {
      bestDist = d;
      best = candidate;
    }
  }
  return bestDist <= MAX_SUPPLIER_DISTANCE ? best : undefined;
}

// leadtime.Days for a (possibly misspelled) supplier name, or undefined when unknown.
function leadDays(supplier: string): number | undefined {
  const name = resolveSupplier(supplier);
  return name === undefined ? undefined : LEAD_DAYS.get(name);
}

// stats.mean: arithmetic mean, 0 for an empty list.
function mean(values: number[]): number {
  if (values.length === 0) return 0;
  let sum = 0;
  for (const v of values) sum += v;
  return sum / values.length;
}

// stats.percentile: nearest rank on the sorted values, p in 0..100, 0 for an empty list.
function percentile(values: number[], p: number): number {
  if (values.length === 0) return 0;
  const v = [...values].sort((a, b) => a - b);
  const rank = Math.max(1, Math.ceil((p / 100) * v.length));
  return v[Math.min(rank, v.length) - 1];
}

// Packs.RoundUp: smallest multiple of packSize that is at least quantity.
function roundUp(quantity: number, packSize: number): number {
  if (packSize <= 0) throw new Error('pack size must be positive');
  if (quantity <= 0) return 0;
  return Math.floor((quantity + packSize - 1) / packSize) * packSize;
}

// dates.add_days: the ISO date the given number of days after iso_date (UTC calendar).
function addDays(isoDate: string, days: number): string {
  const t = Date.parse(isoDate + 'T00:00:00Z') + days * DAY_MS;
  return new Date(t).toISOString().slice(0, 10);
}

// dates.to_weekday: the date itself on Monday to Friday, else the following Monday.
function toWeekday(isoDate: string): string {
  let t = Date.parse(isoDate + 'T00:00:00Z');
  for (;;) {
    const dow = new Date(t).getUTCDay(); // 0 = Sunday, 6 = Saturday
    if (dow !== 0 && dow !== 6) break;
    t += DAY_MS;
  }
  return new Date(t).toISOString().slice(0, 10);
}

// Whole days from a to b for two ISO dates (b - a).
function dayDiff(a: string, b: string): number {
  return Math.round((Date.parse(b + 'T00:00:00Z') - Date.parse(a + 'T00:00:00Z')) / DAY_MS);
}

// weeks.iso_week: ISO week number (1-53) of an ISO date.
function isoWeek(isoDate: string): number {
  const t = new Date(Date.parse(isoDate + 'T00:00:00Z'));
  const dayNum = t.getUTCDay() || 7; // Monday = 1 ... Sunday = 7
  t.setUTCDate(t.getUTCDate() + 4 - dayNum); // Thursday of the same ISO week
  const yearStart = Date.UTC(t.getUTCFullYear(), 0, 1);
  return Math.ceil(((t.getTime() - yearStart) / DAY_MS + 1) / 7);
}

// Seasonal uplift applied to the forecast in ISO weeks 48 to 52.
const SEASON_WEEKS_FROM = 48;
const SEASON_WEEKS_TO = 52;
const SEASON_FACTOR = 1.25;

function compareStrings(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

function run(input: Input): Output {
  const today = input.today;

  const salesBySku = new Map<string, Sale[]>();
  for (const s of input.sales) {
    const list = salesBySku.get(s.sku);
    if (list) list.push(s);
    else salesBySku.set(s.sku, [s]);
  }

  const orders: Record<string, Order> = {};
  const unknown: string[] = [];

  for (const item of input.items) {
    const lead = leadDays(item.supplier);
    if (lead === undefined) {
      unknown.push(item.sku);
      continue;
    }

    // Daily series: index 0 is today - 28, index 27 is yesterday.
    const series: number[] = new Array<number>(WINDOW).fill(0);
    for (const s of salesBySku.get(item.sku) ?? []) {
      const offset = dayDiff(today, s.date); // -28..-1 inside the window
      if (offset >= -WINDOW && offset <= -1) {
        series[offset + WINDOW] += s.qty;
      }
    }

    // Forecast: trailing mean of the last 7 days (stats.trailing_mean with window 7).
    let forecast = mean(series.slice(Math.max(0, WINDOW - TRAILING_WINDOW)));
    const week = isoWeek(today);
    if (week >= SEASON_WEEKS_FROM && week <= SEASON_WEEKS_TO) {
      forecast = forecast * SEASON_FACTOR;
    }
    const safety = percentile(series, 90);
    const need = forecast * (lead + 7) + safety - item.stock;

    if (need > 0) {
      const qty = roundUp(Math.ceil(need), item.pack);
      // Orders below the minimum value are not placed (and the item is still known).
      if (qty * item.price >= MIN_ORDER_SEK) {
        orders[item.sku] = { qty, arrive: toWeekday(addDays(today, lead)) };
      }
    }
  }

  unknown.sort(compareStrings);
  return { orders, unknown };
}

function main(): void {
  const raw = fs.readFileSync(0, 'utf8');
  const input = JSON.parse(raw) as Input;
  const output = run(input);
  process.stdout.write(JSON.stringify(output) + '\n');
}

main();
