// Count each supplied or returned text as its own segment with the same vocabulary.
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const { encode } = await import(process.argv[2] || "gpt-tokenizer/encoding/o200k_base");
const root = fileURLToPath(new URL("./", import.meta.url));
const fixtures = JSON.parse(execFileSync("python", ["-c",
  "import json, tasks; print(json.dumps([tasks.TASKS, tasks.COMMON, tasks.CARDS]))"
], { cwd: root, encoding: "utf8" }));
const [tasks, common, cards] = fixtures;
const runs = JSON.parse(readFileSync(new URL("results.json", import.meta.url), "utf8"));
const tokens = text => encode(text).length;
for (const run of runs) {
  const task = tasks[run.task];
  const guide = tokens(common + "\n" + cards[run.arm] + "\n");
  const requirements = tokens(task.brief + "\n");
  const starter = tokens(task.source);
  let written = 0;
  let feedback = 0;
  for (const attempt of run.attempts) {
    written += tokens(readFileSync(new URL("submissions/" + attempt.file, import.meta.url), "utf8"));
    feedback += tokens(attempt.feedback);
  }
  console.log(JSON.stringify({run: run.id, guide, requirements, starter, written, feedback,
    total: guide + requirements + starter + written + feedback}));
}
