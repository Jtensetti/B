// Reorder suggestions for the furniture warehouse.
//
// The arithmetic and rules live in the libraries under libs/ (Go, Rust, C#, Python).
// They are reached through the small bridge programs under bridge/, each called
// once per run with a batch of requests.

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import * as path from "node:path";
import { distance } from "fastest-levenshtein";

interface Item {
  sku: string;
  supplier: string;
  stock: number;
  pack: number;
  price: number;
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

const BRIDGE = path.join(path.dirname(path.resolve(process.argv[1])), "bridge");
const WINDOW = 28;
const SERVICE_BUFFER_DAYS = 7;
const SAFETY_PERCENTILE = 90;
const FORECAST_WINDOW = 7;
const MIN_ORDER_VALUE = 500;

function run(cmd: string, args: string[], cwd: string, input: string): string {
  const r = spawnSync(cmd, args, {
    cwd,
    input,
    encoding: "utf8",
    maxBuffer: 256 * 1024 * 1024,
    env: { ...process.env, PYTHONDONTWRITEBYTECODE: "1" },
  });
  if (r.error) throw r.error;
  if (r.status !== 0) {
    throw new Error(`${cmd} exited with ${r.status}: ${r.stderr}`);
  }
  return r.stdout;
}

// Calendar helpers (libs/weeks), called as a batch; results come back in request order.
type CalendarRequest =
  | { op: "add_days"; date: string; days: number }
  | { op: "iso_week"; date: string }
  | { op: "to_weekday"; date: string };

function calendar(requests: CalendarRequest[]): (string | number)[] {
  if (requests.length === 0) return [];
  const out = run(
    "python3",
    ["-B", path.join(BRIDGE, "py", "bridge.py")],
    BRIDGE,
    JSON.stringify({ requests }),
  );
  const parsed = JSON.parse(out) as { results: (string | number)[] };
  return parsed.results;
}

function addDays(requests: { date: string; days: number }[]): string[] {
  return calendar(
    requests.map((r) => ({ op: "add_days" as const, date: r.date, days: r.days })),
  ) as string[];
}

// Season: ISO weeks 48 to 52 lift the forecast.
const SEASON_WEEKS = [48, 52] as const;
const SEASON_FACTOR = 1.25;

// Known supplier names (libs/leadtime Suppliers()).
function knownSuppliers(): string[] {
  const out = run(
    "go",
    ["run", "."],
    path.join(BRIDGE, "go"),
    JSON.stringify({ list: true }),
  );
  return (JSON.parse(out) as { suppliers: string[] }).suppliers;
}

// Maps a supplier name as written to a known name: the closest known name at distance
// at most 2 (ties: alphabetically first), or undefined when none is that close.
function canonicalSupplier(name: string, known: string[]): string | undefined {
  let best: string | undefined;
  let bestDistance = Infinity;
  for (const candidate of [...known].sort(compareText)) {
    const d = distance(name, candidate);
    if (d < bestDistance) {
      best = candidate;
      bestDistance = d;
    }
  }
  return bestDistance <= 2 ? best : undefined;
}

// Lead times (libs/leadtime): supplier -> days, or undefined for an unknown supplier.
function leadDays(suppliers: string[]): Map<string, number> {
  const leads = new Map<string, number>();
  if (suppliers.length === 0) return leads;
  const out = run(
    "go",
    ["run", "."],
    path.join(BRIDGE, "go"),
    JSON.stringify({ suppliers }),
  );
  const parsed = JSON.parse(out) as { results: { ok: boolean; days: number }[] };
  suppliers.forEach((name, i) => {
    const r = parsed.results[i];
    if (r.ok) leads.set(name, r.days);
  });
  return leads;
}

// Demand statistics (libs/stats). Each line is one request; returns one number per line.
function rustStats(lines: string[]): number[] {
  if (lines.length === 0) return [];
  const out = run(
    "cargo",
    ["run", "--quiet", "--manifest-path", path.join(BRIDGE, "rust", "Cargo.toml")],
    BRIDGE,
    lines.join("\n") + "\n",
  );
  return out
    .trim()
    .split("\n")
    .map((s) => Number(s));
}

// Pack rounding (libs/Packaging). Each pair is [quantity, packSize]; returns the rounded value.
function roundUpPacks(pairs: [number, number][]): number[] {
  if (pairs.length === 0) return [];
  const out = run(
    "dotnet",
    ["run", "--project", path.join(BRIDGE, "cs"), "-v", "q", "--nologo"],
    BRIDGE,
    JSON.stringify({ requests: pairs }),
  );
  const parsed = JSON.parse(out.trim().split("\n").pop() ?? "") as {
    results: ({ ok: true; value: number } | { ok: false; error: string })[];
  };
  return parsed.results.map((r) => {
    if (!r.ok) throw new Error(r.error);
    return r.value;
  });
}

function compareText(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}

function main(): void {
  const input = JSON.parse(readFileSync(0, "utf8")) as Input;
  const { today, items, sales } = input;

  // The 28 days before today, oldest first.
  const windowDates = addDays(
    Array.from({ length: WINDOW }, (_, i) => ({ date: today, days: i - WINDOW })),
  );
  const week = calendar([{ op: "iso_week", date: today }])[0] as number;
  const seasonFactor =
    week >= SEASON_WEEKS[0] && week <= SEASON_WEEKS[1] ? SEASON_FACTOR : 1;
  const dayIndex = new Map<string, number>();
  windowDates.forEach((d, i) => dayIndex.set(d, i));

  // Daily series per sku.
  const series = new Map<string, number[]>();
  for (const item of items) {
    if (!series.has(item.sku)) series.set(item.sku, new Array<number>(WINDOW).fill(0));
  }
  for (const sale of sales) {
    const daily = series.get(sale.sku);
    const idx = dayIndex.get(sale.date);
    if (daily !== undefined && idx !== undefined) daily[idx] += sale.qty;
  }

  // Supplier names are matched to the known list first; a name that matches nothing is unknown.
  const suppliers = knownSuppliers();
  const canonical = new Map<string, string | undefined>();
  for (const item of items) {
    if (!canonical.has(item.supplier)) {
      canonical.set(item.supplier, canonicalSupplier(item.supplier, suppliers));
    }
  }
  const leads = leadDays(
    [...new Set([...canonical.values()].filter((v): v is string => v !== undefined))],
  );

  const known: { item: Item; supplier: string }[] = [];
  const unknownSet = new Set<string>();
  for (const item of items) {
    const name = canonical.get(item.supplier);
    if (name !== undefined && leads.has(name)) known.push({ item, supplier: name });
    else unknownSet.add(item.sku);
  }

  // forecast = trailing_mean(series, 7), safety = percentile(series, 90)
  const statLines: string[] = [];
  for (const { item } of known) {
    const values = (series.get(item.sku) ?? []).join(" ");
    statLines.push(`trailing_mean ${FORECAST_WINDOW} ${values}`);
    statLines.push(`percentile ${SAFETY_PERCENTILE} ${values}`);
  }
  const stats = rustStats(statLines);

  // need = forecast * (lead + 7) + safety - stock
  const needing: { item: Item; lead: number; forecast: number; need: number }[] = [];
  known.forEach(({ item, supplier }, k) => {
    const lead = leads.get(supplier) ?? 0;
    const forecast = stats[2 * k] * seasonFactor;
    const safety = stats[2 * k + 1];
    const need = forecast * (lead + SERVICE_BUFFER_DAYS) + safety - item.stock;
    if (need > 0) needing.push({ item, lead, forecast, need });
  });

  // qty = RoundUp(ceil(need), pack)
  const rounded = roundUpPacks(
    needing.map((n): [number, number] => [Math.ceil(n.need), n.item.pack]),
  );

  // Orders worth less than MIN_ORDER_VALUE SEK (qty × price) are not placed.
  const placed = needing
    .map((n, k) => ({ ...n, qty: rounded[k] }))
    .filter((n) => n.qty * n.item.price >= MIN_ORDER_VALUE);

  // arrive = to_weekday(add_days(today, lead))
  const arrivalDays = addDays(placed.map((n) => ({ date: today, days: n.lead })));
  const arrivals = calendar(
    arrivalDays.map((d) => ({ op: "to_weekday" as const, date: d })),
  ) as string[];

  const orders: Record<string, Order> = {};
  placed.forEach((n, k) => {
    orders[n.item.sku] = { qty: n.qty, arrive: arrivals[k] };
  });

  const output: Output = {
    orders,
    unknown: [...unknownSet].sort(compareText),
  };
  process.stdout.write(JSON.stringify(output) + "\n");
}

main();
