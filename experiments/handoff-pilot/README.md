# Does an executable handoff help the next model make the right edit?

Four fresh solver contexts received two matched maintenance tasks. Each task was assigned once with an executable B directive inside the source file and once with an equivalent short English note delivered separately. Each product brief, permitted operations, three-submission budget, public feedback and independent acceptance test were shared between the two conditions.

| Task | Handoff | Note tokens | Source tokens | Total across these two responses | How the solver edited | Independent score on first submission |
| --- | --- | ---: | ---: | ---: | --- | ---: |
| Palette | English | 13 | 56 | 69 | Edited the function | 15/15 |
| Palette | Directive | 11 | 67 | 78 | Applied the directive | 15/15 |
| Display signal | English | 13 | 64 | 77 | Edited the function | 25/25 |
| Display signal | Directive | 11 | 75 | 86 | Edited the function | 25/25 |

All four chose to view both the note and the full source, including the embedded directive in the two directive runs. The paired submissions produced byte-identical source. Each isolated directive used two fewer tokens than the corresponding English note. Each directive run consumed nine more tokens across the two observed responses because the embedded instruction was seen twice. We encoded each actual note and source response separately, including trailing newlines, under `o200k_base` with gpt-tokenizer 4.1.2. The table excludes the common brief, protocol, submission responses, shell editing commands, model reasoning, message framing and time. The model's own billed token usage and the author's costs were unmeasured. [Event and submission records](results.json) · [Tokenizer calculation](../handoff-cost/measure.mjs).

## What applying a directive can decide

The palette handoff asks for shade 3 in zone 6. The executable directive contains the complete change. Applying it directly yields all 15 expected observations without any model editing.

The signal handoff asks for output 8 at phase 3. The common brief also says that channel 0 must retain its diagnostic signal because another program consumes it. The old instruction remains type-correct. Applying it literally passes all three public examples and 24 of 25 independent checks. At phase 3 it changes channel 0 from 13 to 8. Both incoming solvers gave the existing diagnostic requirement priority, kept 13, and implemented the override on the other channels. The fully scoped guard could have been written by the outgoing maintainer if that requirement was already known.

## Protocol and limits

The [product briefs, starts and notes](tasks.py), [solver instructions](PROTOCOL.md), and [independent scorer](score.py) were fixed before solver dispatch. The scorer's SHA-256 is `f70956a70920029c67bff3ecf7c4bffa1e6538644b2fc5cacd495ef8cf8aa4de`. It checks every legal target input for these two small tasks, selected invalid inputs, untouched label results, API types and purity. Each context got its own directory and an instruction to avoid other working directories and the scorer. [Tool interface](tool.py).

The two pairs used the same model defaults and ran in a shared host. Assignment was sequential and each cell contains a single run. The work an author invests in expressing and validating a correct predicate was outside the trial. A programmer with a known exact edit could also send a patch. These results show how narrowly applying an instruction can work and how a plausible stale instruction can fail. They do not establish an advantage in retries or a reduction in total model tokens.

From the repository root with B installed, replay the independent scores and run the normal CLI against fresh copies of both original directives.

```sh
python experiments/handoff-pilot/replay.py
```
