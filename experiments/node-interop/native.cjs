const fs = require("node:fs");
const path = require("node:path/posix");
const semver = require("semver");
const { version } = require("semver/package.json");

const words = require("fastest-levenshtein");
const wordVersion = require("fastest-levenshtein/package.json").version;

const calls = JSON.parse(fs.readFileSync(0, "utf8"));
const libraries = { path, versions: semver, words };
const values = calls.map(([library, name, args]) => libraries[library][name](...args));
process.stdout.write(JSON.stringify({ node: process.version, semver: version, levenshtein: wordVersion, values }));
