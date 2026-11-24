"use strict";
// Bridge to libs-provided fastest-levenshtein. Reads {"pairs": [[a, b], ...]} on stdin,
// writes {"distances": [...]} on stdout.
const path = require("path");
const { distance } = require(path.join(__dirname, "..", "..", "node_modules", "fastest-levenshtein"));

let data = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => (data += chunk));
process.stdin.on("end", () => {
  const req = JSON.parse(data);
  const distances = req.pairs.map((pair) => distance(pair[0], pair[1]));
  process.stdout.write(JSON.stringify({ distances: distances }));
});
