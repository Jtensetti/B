# First use on two changes to one booking program

Two isolated model sessions received the existing booking source, a one-sentence language or library guide and a product request. One used B, one used Python with the equivalent protection helper already available. They supplied one line each. A second request in the same context extended the policy again. The Python author received the unannotated idiomatic fixture. Source inspection outside the supplied packet, tool calls and repairs were excluded from the task. The exact messages, replies and independent scoring logic are in [replay.py](replay.py).

Each author got both changes right on the first submission. At each stage the scorer checked all five booking outputs across 16 inputs and rejected a variant venue whose seat accounting depended on the promotion. The second stage preserves the first change.

| o200k_base text tokens | B | Python |
|---|---:|---:|
| First instructions, original source and request | 229 | 182 |
| First answer | 13 | 16 |
| Follow-up request | 29 | 29 |
| Second answer | 13 | 16 |
| Sum, each new message counted once | 284 | 243 |

The B replies saved six tokens. Reading the first packet cost 47 more. On the follow-up alone, new input and output took 42 tokens in B and 45 in Python. Billing for a model that reprocesses earlier messages can differ. The counts omit system messages, tool envelopes, hidden reasoning, cache rates and model latency. Two sessions on one service with two small additive edits do not estimate a general success rate. The result also excludes the prior creation of both implementations.

Run `python experiments/executable-changes/first-use/replay.py` with B installed. Pass the absolute path to the `gpt-tokenizer` o200k_base ESM encoding to recount the messages. [Full local execution cost and mutation tests](../README.md).

## Supplying the language boundary

Three fresh sessions repeated both changes. [surface.py](surface.py) obtained the B parameter lists from compiled BIR and the corresponding Python names from its syntax tree, including the tuple headings of the set-membership test. Both authors saw the same five relations with the same parameter order. Generating that interface is included in the local replay time. The projection is specific to the shapes supported by this script and omits types. In particular, its notation makes the Python set look like a callable.

| Input in the new session | Initial prompt | All replies, including failed attempts | Follow-up and repair feedback | Total visible tokens | Extra attempts |
|---|---:|---:|---:|---:|---:|
| B interface | 136 | 26 | 29 | 191 | 0 |
| Python interface | 131 | 95 | 91 | 317 | 2 |
| Python interface with typed helper signature | 137 | 32 | 29 | 198 | 0 |

The first Python author passed quoted names, then looked for a captured set inside a function. The actual error messages are included in the counts. After seeing that the target was itself a set the author passed it directly. Giving a fresh Python author the parameter types in the helper signature cost six extra input tokens and both edits succeeded immediately. This control was chosen after seeing the failure. The 191 versus 198 comparison is the more informative estimate on this task.

The warm local replay reads the source, derives the interface where requested, applies the submitted lines, checks both revisions, executes the output oracle and verifies the deliberately miswired venue. Each table entry describes one author session. The timer measures the local parts repeatedly, excluding author inference and any network charges; benchmark instructions and the timer itself are not sent to the models. Run with `--rounds 21` for medians, rotating the replay order. Local latency and generated-text costs can favor different implementations.

Across 21 rotating rounds on CPython 3.12.14, median local replay took 22.98 ms in B and 1.30 ms in Python with full source. With the generated interface, B took 25.09 ms and the typed Python guide took 1.26 ms. In that last comparison B saved one input token and six output tokens. For a serial pipeline, ignoring the saved input token, each avoided output token would need to save about 4 ms to offset the 23.83 ms of extra local work. Actual inference latency, billed tokens and authoring time were unavailable.
