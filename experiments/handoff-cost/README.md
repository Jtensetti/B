# How many tokens does a handoff use?

Reading all 26 example B programs from version 0.13 once took **2,006 tokens** with the `o200k_base` vocabulary. Removing free-form comments reduced the total to **1,597**, a saving of 409 tokens (20.4%). We encoded each file separately. Twenty-one files contained comments. The set includes demonstration code and several variants of the same polyglot example. The saving describes the examples in this repository. A reader that already hides comments would read the same 1,597 tokens under either grammar. The filter preserves hashes inside quoted strings and removes comment-only lines with their line endings.

## The same parcel-routing change

Each handoff asks for `route(5)` to return `"express"`. The unchanged routing function takes 45 tokens. The line includes its final newline. The last column adds the cost of generating the line once to the cost of reading the entire revised file once.

| Handoff | Author writes line | Successor reads line only | Successor reads full file | Author writes line and successor reads full file |
| --- | ---: | ---: | ---: | ---: |
| No instruction | 0 | 0 | 45 | 45 |
| `# When days equals 5, route should return "express".` | 13 | 13 | 58 | 71 |
| `# route: days=5 -> "express"` | 10 | 10 | 55 | 65 |
| `next route when days == 5 => "express"` | 11 | 11 | 56 | 67 |

When the author writes the line and the successor sees only that line, the three handoffs cost 26, 20 and 22 text tokens respectively. Dropping the line entirely also drops the requested change. The instruction in the last row can be applied mechanically. The prose and shorthand require interpretation.

## Text observed by the four pilot solvers

Every solver requested its handoff once and its entire source once. The prose note was delivered separately. The typed note appeared both in the note response and in the source. These counts reconstruct those tool responses from the frozen starters and validate their byte lengths against the four recorded event traces. The final two columns count a single hypothetical response containing the target declaration and its handoff exactly once. For both typed fixtures, the reconstructed text matches the output of the implemented `b next FILE --context` command byte for byte. The pilot solvers did not receive that presentation. [Tasks and outcomes](../handoff-pilot/README.md).

| Task | Prose note + full source, observed | Typed note + full source, observed | Target + prose, hypothetical | Target + typed, hypothetical |
| --- | ---: | ---: | ---: | ---: |
| Shade | 69 | 78 | 54 | 52 |
| Signal | 77 | 86 | 62 | 60 |

Each typed note alone used 11 tokens and the corresponding prose note used 13. Reading the complete file as well made each typed condition nine tokens larger than its prose counterpart. B's `view` command can show one target declaration. `b next FILE --context` pairs each target with its instruction. The equally focused prose comparison measures how much of a reduction comes from selecting a smaller part of the source.

These are counts of text under one vocabulary. The study did not measure billed tokens, prompt caching, tool envelopes, model reasoning, revision output, or the complete interaction. It supplies no estimate of average savings for production repositories.

## Recompute

Run from a Git checkout containing the referenced 0.13 commit, with Node and Python 3 available. The tokenizer is an optional experiment dependency. The measurement uses the `o200k_base` implementation from `gpt-tokenizer` 4.1.2. [Tokenizer revision](https://github.com/niieani/gpt-tokenizer/tree/785c2695acbda31ae31ef8ab6343bcd7f1dde72f) · [Recorded counts](results.json).

```sh
work=$(mktemp -d)
npm install --prefix "$work" --ignore-scripts --no-audit --no-fund gpt-tokenizer@4.1.2
node experiments/handoff-cost/measure.mjs "$work/node_modules/gpt-tokenizer/esm/encoding/o200k_base.js"
```
