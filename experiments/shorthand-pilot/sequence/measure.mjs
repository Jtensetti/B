import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const { encode } = await import(process.argv[2] || "gpt-tokenizer/encoding/o200k_base");
const dir = fileURLToPath(new URL("./", import.meta.url));
const lines = JSON.parse(execFileSync(process.argv[3] || "python",
  ["replay.py", "--packets"], {cwd: dir, encoding:"utf8"}));
for (const row of lines) {
  const values = {};
  for (const k of ["guide", "brief", "source", "generated", "feedback"]) {
    values[k] = row[k].reduce((sum, text) => sum + encode(text).length, 0);
  }
  console.log(JSON.stringify({id: row.id, stage: row.stage, ...values,
    total: Object.values(values).reduce((sum, n) => sum + n, 0),
    matching_canonical_payload: row.canonical === null ? null : encode(row.canonical).length}));
}
