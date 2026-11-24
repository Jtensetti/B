// Reads a JSON array of {"name","names"} and prints the Levenshtein distance from name to each candidate.
const { distance } = require(process.env.LEV_PATH);
let input = "";
process.stdin.on("data", (c) => (input += c));
process.stdin.on("end", () => {
  const reqs = JSON.parse(input);
  const out = reqs.map((r) => r.names.map((n) => distance(r.name, n)));
  process.stdout.write(JSON.stringify(out) + "\n");
});
