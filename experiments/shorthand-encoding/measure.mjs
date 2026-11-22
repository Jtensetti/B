// Quantify surface encodings of the same fixed B 0.14 examples, one file at a time.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const { encode } = await import(process.argv[2] || "gpt-tokenizer/encoding/o200k_base");
const root = fileURLToPath(new URL("../../", import.meta.url));
const revision = "02cd22655f24514d7178f35c527b39664657895a";
const git = (...args) => execFileSync("git", args, { cwd: root, encoding: "utf8" });
const tokens = (s) => encode(s).length;
const files = git("ls-tree", "-r", "--name-only", revision, "--", "examples").trimEnd().split("\n")
  .filter(name => /\.(?:bee|bsrc|b4|b)$/.test(name));
const words = "fn if then else next when pure requires ensures use as let print assert and or not adopt permit foreign cases none true false".split(" ");
const alphabet = [..."ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛋᛏᛒᛖᛗᛚᛜᛞᛟ"];
const rune = new Map(words.map((word, index) => [word, alphabet[index]]));
const wordOrLiteral = /"(?:\\.|[^"\\\r\n])*"|[A-Za-z_][A-Za-z0-9_]*/g;

const totals = { ordinary: 0, omitVowels: 0, runeKeywords: 0 };
for (const name of files) {
  const source = git("show", revision + ":" + name);
  const withoutVowels = source.replace(wordOrLiteral, w => w.startsWith('"') ? w : w.replace(/[aeiouy]/gi, ""));
  const withRunes = source.replace(wordOrLiteral, w => rune.get(w) ?? w);
  // The corpus contains no rune in a literal or identifier.
  assert.equal(withRunes.replace(/[ᚠ-ᛟ]/g, r => words[alphabet.indexOf(r)]), source);
  totals.ordinary += tokens(source);
  totals.omitVowels += tokens(withoutVowels);
  totals.runeKeywords += tokens(withRunes);
}

const shellChanges = [
  'next route when days == 5 => "express"\n',
  'route 5 "express"\n',
  'next signal when phase == 3 => 8\n',
  'signal phase 3 8\n',
];
console.log(JSON.stringify({ files: files.length, totals, rows: shellChanges.map(text => [text.trimEnd(), tokens(text)]) }, null, 2));
