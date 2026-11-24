// Helper for report.py: for each watched package, find the highest released
// version that satisfies its npm semver range (default options).
// Reads {"versions": {pkg: [version, ...]}, "watch": {pkg: range}} on stdin and
// writes {pkg: version} on stdout. Packages with no satisfying release, or with
// an invalid range, are left out.
const path = require("path");
const semver = require(path.join(__dirname, "node_modules", "semver"));

let data = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  data += chunk;
});
process.stdin.on("end", () => {
  const req = JSON.parse(data);
  const out = {};
  for (const [pkg, range] of Object.entries(req.watch || {})) {
    const versions = (req.versions && req.versions[pkg]) || [];
    let best = null;
    try {
      best = semver.maxSatisfying(versions, range);
    } catch (err) {
      best = null;
    }
    if (best !== null) {
      out[pkg] = best;
    }
  }
  process.stdout.write(JSON.stringify(out));
});
