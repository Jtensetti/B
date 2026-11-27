#!/usr/bin/env node
// Deterministic o200k_base token counter using pinned gpt-tokenizer@4.1.2.
import fs from 'node:fs';
import { encode } from './tools/node_modules/gpt-tokenizer/esm/encoding/o200k_base.js';

const args = process.argv.slice(2);
if (args[0] === '--stdin') {
  const text = fs.readFileSync(0, 'utf8');
  console.log(JSON.stringify({ tokens: encode(text).length, bytes: Buffer.byteLength(text, 'utf8') }));
} else if (args.length >= 1) {
  const out = {};
  for (const file of args) {
    const text = fs.readFileSync(file, 'utf8');
    out[file] = { tokens: encode(text).length, bytes: Buffer.byteLength(text, 'utf8') };
  }
  console.log(JSON.stringify(out));
} else {
  console.error('Usage: tokenize_o200k.mjs --stdin | <file...>');
  process.exit(2);
}
