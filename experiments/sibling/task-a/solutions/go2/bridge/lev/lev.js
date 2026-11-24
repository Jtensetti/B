// Reads a JSON array of [a, b] string pairs on stdin, writes a JSON array of
// Levenshtein distances computed by fastest-levenshtein.
const { distance } = require("fastest-levenshtein");

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", () => {
  const pairs = JSON.parse(input);
  process.stdout.write(JSON.stringify(pairs.map(([a, b]) => distance(a, b))));
});
