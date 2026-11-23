// Ground truth for the journey trial, using the libraries the specification names.
import { createRequire } from "node:module";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
const require = createRequire(new URL("../node-interop/package.json", import.meta.url));
const semver = require("semver");
const { distance } = require("fastest-levenshtein");

export function resolve(input, step) {
  const requires = input.requires;
  let available = input.available;
  let pins = step >= 3 ? (input.pins ?? {}) : {};
  if (step >= 8) {
    available = Object.fromEntries(Object.entries(available).map(([name, versions]) => {
      const cleaned = [];
      for (const v of versions) { const c = semver.clean(v); if (c !== null && !cleaned.includes(c)) cleaned.push(c); }
      return [name, cleaned];
    }));
    pins = Object.fromEntries(Object.entries(pins).map(([name, v]) => [name, semver.clean(v) ?? v]));
  }
  const resolved = {}, unresolved = [];
  for (const name of Object.keys(requires)) {
    if (Object.hasOwn(pins, name)) {
      if ((available[name] ?? []).includes(pins[name])) resolved[name] = pins[name];
      else unresolved.push(name);
      continue;
    }
    if (!Object.hasOwn(available, name)) { unresolved.push(name); continue; }
    let candidates = available[name];
    let best;
    if (step >= 6 && requires[name] === "latest") {
      best = semver.maxSatisfying(candidates.filter((v) => semver.valid(v) && !semver.prerelease(v)), "*");
    } else if (step >= 6 && requires[name] === "next") {
      const valid = candidates.filter((v) => semver.valid(v)).sort(semver.compare);
      best = valid.length ? valid[valid.length - 1] : null;
    } else {
      if (step >= 4) candidates = candidates.filter((v) => !semver.prerelease(v));
      best = semver.maxSatisfying(candidates, requires[name]);
    }
    if (best === null) unresolved.push(name); else resolved[name] = best;
  }
  unresolved.sort();
  const out = { resolved, unresolved };
  if (step >= 2) {
    const suggestions = {};
    const names = Object.keys(available).sort();
    for (const name of unresolved) {
      if (Object.hasOwn(available, name) || names.length === 0) continue;
      let best = null, bestDistance = Infinity;
      for (const candidate of names) {
        const d = distance(name, candidate);
        if (d < bestDistance) { best = candidate; bestDistance = d; }
      }
      if (bestDistance <= 2) suggestions[name] = best;
    }
    out.suggestions = suggestions;
  }
  if (step >= 5) {
    out.summary = { resolved: Object.keys(out.resolved).length, unresolved: out.unresolved.length,
                    suggested: Object.keys(out.suggestions).length };
  }
  if (step >= 7) {
    const outdated = {};
    for (const name of Object.keys(out.resolved)) {
      const current = out.resolved[name];
      if (!semver.valid(current)) continue;
      const stable = (available[name] ?? []).filter((v) => semver.valid(v) && !semver.prerelease(v)).sort(semver.compare);
      const top = stable[stable.length - 1];
      if (top !== undefined && semver.gt(top, current)) outdated[name] = top;
    }
    out.outdated = outdated;
  }
  return out;
}

const dir = new URL("./fixtures/", import.meta.url);
const expected = {};
for (const file of readdirSync(dir).filter((f) => f.endsWith(".json") && !f.startsWith("_")).sort()) {
  const input = JSON.parse(readFileSync(new URL(file, dir), "utf8"));
  expected[file] = {};
  for (let step = 1; step <= 8; step++) {
    const fed = step >= 3 ? input : Object.fromEntries(Object.entries(input).filter(([k]) => k !== "pins"));
    expected[file][step] = resolve(fed, step);
  }
}
writeFileSync(new URL("./fixtures/_expected.json", import.meta.url), JSON.stringify(expected, null, 1) + "\n");
console.log(`${Object.keys(expected).length} fixtures`);
