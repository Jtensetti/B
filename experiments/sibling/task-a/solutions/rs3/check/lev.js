const { distance } = require("/tmp/claude-0/-home-user-B/bc1bd2a3-1ba0-5a86-9b4b-8c9b2f90e18b/scratchpad/sibA/rs3/node_modules/fastest-levenshtein/mod.js");
function dp(a, b) {
  const prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    for (let j = 0; j <= b.length; j++) prev[j] = cur[j];
  }
  return prev[b.length];
}
const alphabet = "abcd ";
let bad = 0, n = 0;
function rnd(max) { const L = Math.floor(Math.random() * max); let s = ""; for (let i = 0; i < L; i++) s += alphabet[Math.floor(Math.random() * alphabet.length)]; return s; }
for (let t = 0; t < 200000; t++) {
  const a = rnd(t % 2 ? 12 : 80), b = rnd(t % 3 ? 12 : 80);
  n++;
  if (distance(a, b) !== dp(a, b)) { bad++; if (bad < 5) console.log("MISMATCH", JSON.stringify(a), JSON.stringify(b), distance(a, b), dp(a, b)); }
}
console.log("pairs", n, "mismatches", bad);
