// Batch helper: argv[2] is the semver package directory. Reads a JSON array of contract
// versions on stdin and writes a JSON array of booleans: does each satisfy argv[3]?
const path = require("path");
const semver = require(path.resolve(process.argv[2]));
const range = process.argv[3];
let data = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (data += chunk));
process.stdin.on("end", () => {
  const versions = JSON.parse(data);
  process.stdout.write(JSON.stringify(versions.map((v) => semver.satisfies(v, range))));
});
