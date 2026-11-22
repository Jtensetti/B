// Print a deterministic source-text token census, with each file encoded separately.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const { encode } = await import(process.argv[2] || "gpt-tokenizer/encoding/o200k_base");
const root = fileURLToPath(new URL("../../", import.meta.url));
const revision = "1cbf1fb8a71ae048e7ba5602ba2d37c96e4f9a09";
const git = (...args) => execFileSync("git", args, { cwd: root, encoding: "utf8" });
const count = (value) => encode(value).length;
assert.deepEqual([...encode("antidisestablishmentarianism")], [493, 129901, 376, 160388, 21203, 2367]);

function withoutComments(source) {
  // The second alternative consumes a quoted string before any # inside it.
  // Remove the newline of a comment-only line, preserving all other line breaks.
  return source.replace(/^[ \t]*#[^\r\n]*(?:\r?\n|$)|"(?:\\.|[^"\\\r\n])*"|[ \t]*#[^\r\n]*/gm,
    (part) => part.startsWith('"') ? part : "");
}

assert.equal(withoutComments('print "# keep"  # remove\r\n # remove\r\n'), 'print "# keep"\r\n');
assert.equal(withoutComments(String.raw`print "a\"#b" # remove`), String.raw`print "a\"#b"`);
assert.equal(withoutComments("# remove\n\nprint 1\n"), "\nprint 1\n");

const paths = git("ls-tree", "-r", "--name-only", revision, "--", "examples").trimEnd().split("\n")
  .filter((path) => /\.(?:b|b4|bee|bsrc)$/.test(path));
const corpus = { files: paths.length, files_with_comments: 0, full_tokens: 0, filtered_tokens: 0 };
for (const path of paths) {
  const source = git("show", revision + ":" + path);
  const filtered = withoutComments(source);
  if (filtered !== source) corpus.files_with_comments++;
  corpus.full_tokens += count(source);
  corpus.filtered_tokens += count(filtered);
}

const body = withoutComments(git("show", revision + ":examples/registers/dispatch.bee"));
const variants = {
  no_handoff: "",
  prose: '# When days equals 5, route should return "express".\n',
  shorthand: '# route: days=5 -> "express"\n',
  directive: 'next route when days == 5 => "express"\n',
};
const matched = {};
for (const [key, line] of Object.entries(variants)) {
  matched[key] = {
    line,
    author_writes_line: count(line),
    successor_reads_line_only: count(line),
    successor_reads_full_file: count(body + line),
    author_line_plus_successor_line: 2 * count(line),
    author_line_plus_successor_full_file: count(line) + count(body + line),
  };
}
// Obtain the archived strings directly from the pilot. Validate reconstructed
// displays against the byte lengths observed by its wrapper before counting.
const pilotDir = fileURLToPath(new URL("../handoff-pilot/", import.meta.url));
const tasks = JSON.parse(execFileSync("python3", ["-c", "import json; from tasks import TASKS; print(json.dumps(TASKS))"],
  { cwd: pilotDir, encoding: "utf8" }));
const records = JSON.parse(readFileSync(new URL("../handoff-pilot/results.json", import.meta.url), "utf8"));
const pilot = records.map((run) => {
  const task = tasks[run.task];
  const typed = run.handoff === "typed";
  const line = (typed ? task.directive : task.prose) + "\n";
  const prefix = task.starter + (typed ? line : "");
  const reads = { note: 0, source: 0 };
  for (const event of run.events.filter((e) => e.action === "note" || e.action === "source")) {
    const displayed = event.action === "note" ? line : prefix;
    assert.equal(Buffer.byteLength(displayed), event.visible_bytes, run.id + "/" + event.action);
    reads[event.action] += count(displayed);
  }
  // Both frozen targets are one-line declarations; this models a single
  // display containing just the declaration and the applicable note.
  const declaration = task.starter.split("\n").find((s) => s.startsWith("fn " + run.task + "("));
  assert.ok(declaration, run.task);
  return {
    id: run.id, task: run.task, handoff: run.handoff, ...reads, total: reads.source + reads.note,
    hypothetical_target_and_note: count(declaration + "\n" + line),
  };
});
console.log(JSON.stringify({ encoding: "o200k_base", revision, corpus, matched, pilot }, null, 2));
