import { createRequire } from "node:module";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
const require = createRequire(new URL("../node-interop/package.json", import.meta.url));
const semver = require("semver");

export function isoWeek(text) {
  const [y, m, d] = text.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d));
  const day = (date.getUTCDay() + 6) % 7;            // Monday = 0
  date.setUTCDate(date.getUTCDate() - day + 3);      // Thursday of this week
  const year = date.getUTCFullYear();
  const jan4 = new Date(Date.UTC(year, 0, 4));
  const week = 1 + Math.round(((date - jan4) / 86400000 - 3 + ((jan4.getUTCDay() + 6) % 7)) / 7);
  return `${year}-W${String(week).padStart(2, "0")}`;
}
const days = (a, b) => (Date.parse(b + "T00:00:00Z") - Date.parse(a + "T00:00:00Z")) / 86400000;

export function report(input, step) {
  const kept = step >= 7 ? input.releases.filter((r) => days(r.date, input.today) >= 0) : input.releases;
  const byPackage = {};
  for (const r of kept) (byPackage[r.package] ??= []).push(r);
  const latest = {}, majors = {};
  for (const [name, rs] of Object.entries(byPackage)) {
    const stable = rs.filter((r) => !semver.prerelease(r.version));
    if (!stable.length) continue;
    const top = stable.reduce((a, b) => (semver.gt(b.version, a.version) ? b : a));
    latest[name] = { version: top.version, date: top.date };
    majors[name] = new Set(stable.map((r) => semver.major(r.version))).size;
  }
  const out = { latest };
  if (step >= 2) {
    const weekly = {};
    for (const r of kept) {
      if (step >= 6 && semver.prerelease(r.version)) continue;
      const w = isoWeek(r.date); weekly[w] = (weekly[w] ?? 0) + 1;
    }
    out.weekly = weekly;
  }
  const limit = (n) => (step >= 8 && Object.hasOwn(input.stale_overrides ?? {}, n) ? input.stale_overrides[n] : input.stale_days);
  if (step >= 3) out.stale = Object.keys(latest).filter((n) => days(latest[n].date, input.today) > limit(n)).sort();
  if (step >= 4) {
    const watched = {};
    for (const [name, range] of Object.entries(input.watch ?? {})) {
      const best = semver.maxSatisfying((byPackage[name] ?? []).map((r) => r.version), range);
      if (best !== null) watched[name] = best;
    }
    out.watched = watched;
  }
  if (step >= 5) out.majors = majors;
  if (step >= 9) out.since = Object.fromEntries(Object.keys(latest).map((n) => [n, days(latest[n].date, input.today)]));
  return out;
}

if (process.argv[2]) {
  const dir = process.argv[2];
  const expected = {};
  for (const f of readdirSync(dir).filter((f) => f.endsWith(".json") && !f.startsWith("_")).sort()) {
    const input = JSON.parse(readFileSync(`${dir}/${f}`, "utf8"));
    expected[f] = {};
    for (let s = 1; s <= 9; s++) {
      const fed = { ...input };
      if (s < 3) { delete fed.today; delete fed.stale_days; }
      if (s < 4) delete fed.watch;
      if (s < 8) delete fed.stale_overrides;
      expected[f][s] = report(fed, s);
    }
  }
  writeFileSync(`${dir}/_expected.json`, JSON.stringify(expected, null, 1) + "\n");
  console.log(Object.keys(expected).length + " fixtures");
}
