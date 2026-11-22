# One executable rule change, two domains

An accepted booking program admits children free on Saturday. This B declaration extends the rule to Sunday and names the functions whose behavior must stay independent of that rule.

```bee
also free_entry(true, "sun") keeping seats, recipient
```

The gate receives the accepted program and this exact declaration as its authority. The same line is appended to the program and runs through the normal compiler. A child's Sunday price changes from 100 to 0, and the cart total automatically follows. An unrelated source edit that debits two seats on Sunday fails a public-function comparison. A pre-existing call from `seats` to `price`, which calls `free_entry`, fails the dependency check even when the candidate contains only the requested edit. Without `keeping`, that inherited dependency really does debit two seats in the experiment.

The second task adds a reference sensor's setup readings to a discard rule. Sums change automatically and the sample counter continues to count discarded readings. Both fixtures are pure modules. Seats and receipt recipients represent decisions that a caller could later act upon.

## Controls and results

[check.py](check.py) runs the B compiler and the Python implementations against the same independent application definitions. Each pair of booking or sensor events feeds the state produced by the first event into the second. The Python comparator uses an ordinary set and a reusable `also(table, fact, *keeping)` operation. Its checker compares Python syntax trees to the accepted program plus the edit and seeks a concrete differing result if the trees differ. The observer protection follows global references between the functions used in these fixtures. This Python implementation executes trusted benchmark files and assumes their simple, direct data access patterns. The B checker also supports equivalence proofs over a limited scalar expression fragment.

| Task | Individual function observations | Two-event sequences | Rejected candidates per implementation |
| --- | ---: | ---: | --- |
| Booking | 128 | 256 | Missing edit, two seats debited, incorrect recipient, stale cart total, inherited seat dependency |
| Sensor readings | 189 | 729 | Missing edit, discarded reading reduces sample count, relabeled sensor |

B, plain Python and type-annotated Python each passed all 317 observations and 985 sequences and rejected all eight bad candidates. Both B's checker and the Python comparator produced concrete behavioral differences for the seven incorrect candidate implementations. Both rejected the inherited dependency. The valid changes were supplied by the benchmark author. A [two-edit author experiment](first-use/README.md) measures actual submissions and retries with either full source or an automatically derived interface. A [scaling experiment](indexed/README.md) compares compiled tuple membership at up to 512 facts.

The following are median milliseconds on CPython 3.12.14 with one warm-up per implementation and 21 measured rounds, rotating their order. The first time starts just before reading the local accepted source file and includes appending the declaration and checking it against the pinned change. The second includes a fresh compilation/load and execution of all the independent observations and event sequences. Python's annotations provide type information to a reader. Python's timer includes loading those annotations and skips a separate static checker. B performs its native static checks and also guards its public calls at runtime.

| Task | Implementation | Read, edit and check | Including execution and independent oracle |
| --- | --- | ---: | ---: |
| Booking | B | 5.77 | 8.77 |
| Booking | Python | 0.52 | 0.85 |
| Booking | Python with type annotations | 0.64 | 0.99 |
| Sensor readings | B | 6.06 | 10.12 |
| Sensor readings | Python | 0.53 | 1.10 |
| Sensor readings | Python with type annotations | 0.65 | 1.30 |

## Tokens and the cost boundary

The fixed-packet study uses `o200k_base`. Each segment is encoded separately, including trailing newlines. The full packet consists of the task, existing source, declaration and a normalized two-token success verdict. The indexed packet replaces the source with the same hand-prepared card of names, parameter order and relevant literals for all implementations. Each declaration is transmitted once. The workflow reuses it for both execution and checking. With Python type annotations, Python's declared public types largely account for the extra cost of reading B in the full-source comparison.

| Task | Implementation | Existing source | Declaration | Full packet | Indexed packet |
| --- | --- | ---: | ---: | ---: | ---: |
| Booking | B | 126 | 13 | 156 | 56 |
| Booking | Python | 84 | 15 | 116 | 58 |
| Booking | Python with type annotations | 127 | 15 | 159 | 58 |
| Sensor readings | B | 125 | 11 | 154 | 51 |
| Sensor readings | Python | 79 | 12 | 109 | 52 |
| Sensor readings | Python with type annotations | 123 | 12 | 153 | 52 |

The unprotected booking edit alone costs eight tokens in B and nine for Python's built-in `free_entry.add((True, "sun"))`. The protected form requires a reusable checker in both languages. The table assumes these tools are already installed and the author knows their interfaces. It excludes preparing the card, fetching context, learning the tools, model inference, retries and deployment. The two model-visible token savings in the indexed booking example come with about 7.9 milliseconds of additional local execution and oracle time on this machine. In a serial pipeline with identical input processing, saving two output tokens would cover that delay if each avoided output token took over 4 milliseconds. That is a conditional crossover using these measurements. No model latency or invoice was measured here. A workflow which supplies the complete unannotated Python source uses fewer visible tokens and completes faster in Python on both tasks.

## Reproduce

From the repository root with B installed, run:

```sh
python experiments/executable-changes/check.py --rounds 21
```

Token counts additionally use gpt-tokenizer 4.1.2. To run the same checks and print all token segments:

```sh
work=$(mktemp -d)
npm install --prefix "$work" --ignore-scripts --no-audit --no-fund gpt-tokenizer@4.1.2
python experiments/executable-changes/check.py --rounds 21 --tokenizer "$work/node_modules/gpt-tokenizer/esm/encoding/o200k_base.js"
```
