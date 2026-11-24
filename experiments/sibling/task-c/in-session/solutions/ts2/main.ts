import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
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

const root = path.dirname(process.argv[1]);
const bridgeDir = (name: string): string => path.join(root, "bridge", name);

// Runs a helper program with the given lines on stdin and returns its non-empty stdout lines.
function runLines(cmd: string, args: string[], cwd: string, lines: string[]): string[] {
  const r = spawnSync(cmd, args, {
    cwd,
    input: lines.join("\n") + "\n",
    encoding: "utf8",
    maxBuffer: 64 * 1024 * 1024,
  });
  if (r.error) throw r.error;
  if (r.status !== 0) {
    throw new Error(`${cmd} exited with ${r.status}: ${r.stderr}`);
  }
  return r.stdout.split("\n").filter((l) => l.length > 0);
}

function mean(values: number[]): number {
  return values.length === 0 ? 0 : values.reduce((a, b) => a + b, 0) / values.length;
}

const input = JSON.parse(fs.readFileSync(0, "utf8")) as Input;
const WINDOW = 28;

// 1. Delivery days for every supplier in the roster (Go leadtime library). Each supplier name is
// matched to the closest roster name (distance at most 2, ties alphabetical).
const roster = runLines("go", ["run", "."], bridgeDir("go"), ["all"]).map((l) => {
  const [name, d] = l.split("\t");
  return { name, lead: d === "ERR" ? null : Number(d) };
});
const leadByRosterName = new Map<string, number | null>(roster.map((r) => [r.name, r.lead]));

function matchSupplier(raw: string): string | null {
  let best: string | null = null;
  let bestDist = Infinity;
  for (const r of roster) {
    const d = distance(raw, r.name);
    if (d < bestDist || (d === bestDist && best !== null && r.name < best)) {
      best = r.name;
      bestDist = d;
    }
  }
  return bestDist <= 2 ? best : null;
}

const suppliers = [...new Set(input.items.map((it) => it.supplier))];
const leadBySupplier = new Map<string, number | null>();
for (const s of suppliers) {
  const canonical = matchSupplier(s);
  leadBySupplier.set(s, canonical === null ? null : leadByRosterName.get(canonical) ?? null);
}

const known = input.items.filter((it) => leadBySupplier.get(it.supplier) != null);
const unknown = input.items
  .filter((it) => leadBySupplier.get(it.supplier) == null)
  .map((it) => it.sku)
  .sort();

// 2. ISO week of today, the 28 days before today, and the weekday arrival date of each known item (Python weeks library).
const offsets: number[] = [];
for (let k = -WINDOW; k < 0; k++) offsets.push(k);
const dateLines = [
  `week ${input.today}`,
  ...offsets.map((k) => `add ${input.today} ${k}`),
  ...known.map((it) => `arrive ${input.today} ${leadBySupplier.get(it.supplier)}`),
];
const dateOut = dateLines.length > 0
  ? runLines("python3", ["-I", path.join(bridgeDir("py"), "bridge.py")], root, dateLines)
  : [];
const isoWeek = Number(dateOut[0]);
const windowDates = dateOut.slice(1, 1 + WINDOW);
const arriveBySku = new Map<number, string>();
known.forEach((_, i) => arriveBySku.set(i, dateOut[1 + WINDOW + i]));

// 3. Daily sales per sku and date, summed over the window.
const sold = new Map<string, number>();
const windowSet = new Set(windowDates);
for (const sale of input.sales) {
  if (!windowSet.has(sale.date)) continue;
  const key = `${sale.sku}\u0000${sale.date}`;
  sold.set(key, (sold.get(key) ?? 0) + sale.qty);
}
const series = known.map((it) =>
  windowDates.map((d) => sold.get(`${it.sku}\u0000${d}`) ?? 0),
);

// 4. Trailing 7-day mean (forecast) and 90th percentile (safety) of each series (Rust stats library).
const statLines = series.length > 0
  ? runLines("cargo", ["run", "-q"], bridgeDir("rust"), series.map((s) => s.join(" ")))
  : [];
const stats = statLines.map((l) => {
  const [, p, t] = l.split(" ");
  return { forecast: Number(t), safety: Number(p) };
});

// 5. Need per item; the items that need stock get a pack-rounded quantity (C# Packaging library).
const needs = known.map((it, i) => {
  const lead = leadBySupplier.get(it.supplier) as number;
  const { forecast: trailing, safety } = stats[i];
  // Peak season (ISO weeks 48 to 52) sells more.
  const forecast = isoWeek >= 48 && isoWeek <= 52 ? trailing * 1.25 : trailing;
  const need = forecast * (lead + 7) + safety - it.stock;
  return { item: it, need, lead, index: i };
});
const toOrder = needs.filter((n) => n.need > 0);
const packOut = toOrder.length > 0
  ? runLines(
      "dotnet",
      ["run", "--nologo", "-v", "q"],
      bridgeDir("cs"),
      toOrder.map((n) => `${Math.ceil(n.need)} ${n.item.pack}`),
    )
  : [];

const orders: Record<string, Order> = {};
toOrder.forEach((n, i) => {
  const qty = Number(packOut[i]);
  // Orders worth less than 500 SEK are not placed.
  if (qty * n.item.price < 500) return;
  orders[n.item.sku] = {
    qty,
    arrive: arriveBySku.get(n.index) as string,
  };
});

const output: Output = { orders, unknown };
process.stdout.write(JSON.stringify(output) + "\n");
