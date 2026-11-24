// Driver: reads a JSON array of version strings on stdin and writes a JSON array of
// booleans telling whether each satisfies the range given as the first argument.
const semver = require("../../node_modules/semver");

const range = process.argv[2];
let data = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (data += chunk));
process.stdin.on("end", () => {
  const versions = JSON.parse(data);
  const out = versions.map((v) => semver.satisfies(v, range));
  process.stdout.write(JSON.stringify(out) + "\n");
});
