import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const { encode } = await import(pathToFileURL(resolve(process.argv[2])).href);
const texts = JSON.parse(readFileSync(0, "utf8"));
console.log(JSON.stringify(Object.fromEntries(
  Object.entries(texts).map(([name, text]) => [name, encode(text).length])
)));
