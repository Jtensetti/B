// Bridge: reads a JSON array of [version, range] pairs on stdin and writes a JSON array
// of booleans using the npm semver package in node_modules (semver.satisfies).
const path = require("path");
const semver = require(path.join(__dirname, "..", "..", "node_modules", "semver"));

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (input += chunk));
process.stdin.on("end", () => {
  const pairs = JSON.parse(input);
  const out = pairs.map(([version, range]) => semver.satisfies(version, range));
  process.stdout.write(JSON.stringify(out));
});
