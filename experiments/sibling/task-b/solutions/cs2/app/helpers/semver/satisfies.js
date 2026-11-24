// Reads one JSON pair [version, range] per line from stdin and writes "true" or "false" per line,
// using the npm semver package in the workspace node_modules.
const fs = require('fs');
const path = require('path');

const ws = process.argv[2];
const semver = require(path.join(ws, 'node_modules', 'semver'));

const lines = fs.readFileSync(0, 'utf8').split('\n').filter((l) => l.length > 0);
const out = lines.map((line) => {
  const [version, range] = JSON.parse(line);
  return semver.satisfies(version, range) ? 'true' : 'false';
});
process.stdout.write(out.map((s) => s + '\n').join(''));
