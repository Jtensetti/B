# Producing maintenance edits with optional shorthand

A dispatch program needed four literal exceptions. The changes affected a bell, lamp, label containing a quoted hash, and a two-argument function depending on the depot. A second program needed a calculation over a time window that exempted service station zero. Each solver received an existing program and a product request. The incoming model authored its own submitted edit.

## Results

| Change | Editing tools available | First submitted edit accepted | Form actually written | Submitted tokens per run | Counted exchange tokens per run |
| --- | --- | ---: | --- | --- | --- |
| Four dispatch exceptions | Ordinary B | 2/2, each 44/44 | Ordinary directives | 46, 46 | 397, 397 |
| Four dispatch exceptions | Ordinary B plus shorthand | 2/2, each 44/44 | Compact rows | 27, 27 | 430, 430 |
| Station/time window | Ordinary B | 2/2, each 42/42 | Ordinary directive | 29, 24 | 318, 313 |
| Station/time window | Ordinary B plus shorthand | 2/2, each 42/42 | Ordinary directive | 29, 24 | 370, 365 |

Both optional dispatch solvers named the second argument of the two-parameter function and omitted the parameter on each single-argument target. Both optional station solvers switched immediately to ordinary B for a conjunction and a calculated result. No run needed a repair. Four distinct submitted texts account for eight runs.

Under `o200k_base`, each four-row batch saved 19 of 46 submitted tokens (41%). The optional guide also cost 52 extra tokens up front (204 versus 152). For a new context that reads each supplied item once, the counted exchange on the dispatch task grew by 33 tokens. On the window task it grew by 52. The exchange column sums the guide, product brief, starter, actual submissions and public feedback, counting each as a separate text segment. Shell commands, tool framing, private reasoning, time, model-specific billing and guide authoring were unmeasured.

The first round alone favors the shorter ordinary guide. A [follow-up in two of the same contexts](sequence/README.md) measured three successive dispatch batches, carrying earlier edits forward and loading the guide once. Both completed every edit on their first submission. Across the three batches the shorthand context used 631 counted tokens, compared with 794 for the ordinary context. Replacing one voluntarily full-file response with equivalent ordinary directives gives 636 as a separate comparison.

## Protocol

Eight fresh model contexts, two per combination of task and tool availability, received the same request, starter and public-feedback limits for the same task. Both arms could use ordinary B pending edits or submit a full B replacement. The optional arm also received a short-format guide and could use the production shorthand interpreter. The optional arm could fall back to ordinary B even on the first submission. The two-attempt limit counted unsuccessful parses as attempts. Solvers stopped at public acceptance. Their submissions were scored independently afterwards.

The dispatch oracle checked 44 observations, including every legal input and selected out-of-domain calls. The station oracle checked 42. Both checked function interfaces and purity. A wrong parameter that happens to match the public example scores 39/44 on dispatch. Removing the service-station exception passes the public window examples but scores 38/42 independently. An additional control sends an implicit choice to a function with two eligible parameters and expects a compiler rejection.

The independent scorer, both product requests, source programs, syntax cards and submission script were frozen before the first solver was dispatched. The original SHA-256 of `score.py` is `0306afc7e4ac2832e4b666631618e75317c366f84eb66a85438b64a61131afe9`. The `tasks.py` digest is `9db9e2c65e7fae536e483a4abd7876f5b1364f179df86b4c8f50284932b75ea5`. Four ordinary-only contexts were dispatched first while the compact CLI was being built. The optional contexts used the actual CLI following a production preflight. Each solver had a separate directory and an instruction to keep to its own files. Model settings were shared, and no model build was pinned. These two chosen tasks and the sequential assignments limit generalization.

## Replay

Run `python experiments/shorthand-pilot/replay.py` with B installed to rescore the archived submissions, controls and parser rejection. To reproduce source-text tokens with `o200k_base`, pass the tokenizer module used by the [handoff cost experiment](../handoff-cost/README.md) to `node experiments/shorthand-pilot/measure.mjs /absolute/path/to/esm/encoding/o200k_base.js`. [Inputs and syntax cards](tasks.py) · [Independent scorer](score.py) · [Run records](results.json).
