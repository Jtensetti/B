# Indexed rule additions

A B predicate with many exact scalar input tuples can search a constant index. The Python backend recognizes the union of equality tests over all the function's guarded parameters, in parameter order. At 32 or more rows it emits membership in a literal set. The original typed BIR remains the input to the revision checker. Functions with fewer additions or other kinds of comparisons use their original expression.

Run from the repository root with B installed:

```sh
PYTHONHASHSEED=0 python experiments/executable-changes/indexed/measure.py
```

Each generated rule accepts `(Int, Text)` and has a false fallback. Half of the 1,024 shuffled queries hit. One quarter miss by number and one quarter miss by text on a known number. Every backend is checked against all 1,024 independent expected Booleans. Lookup times are medians of nine interleaved rounds of 4,096 calls. Build times are medians of five parser-warm compile-and-load runs. The scan comparison uses the same B source, BIR and Python backend with its index threshold set above the number of facts.

Local sample on CPython 3.12.14, x86-64, with hash seed 0:

| Facts | B scan, ns/call | B adaptive, ns/call | Python set, ns/call | Python set with B boundary checks, ns/call | B scan build, ms | B adaptive build, ms |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 211 | 239 | 66 | 226 | 0.78 | 0.61 |
| 16 | 274 | 291 | 76 | 215 | 2.37 | 2.61 |
| 32 | 340 | 225 | 69 | 226 | 4.10 | 3.26 |
| 64 | 482 | 231 | 73 | 220 | 7.63 | 5.89 |
| 256 | 1,453 | 245 | 79 | 243 | 29.04 | 22.05 |
| 512 | 3,598 | 259 | 77 | 239 | 67.12 | 43.07 |

At 512 facts the serialized function code including constants fell from 16,021 to 6,376 bytes. This measures the marshalled function, excluding interpreter and live heap memory. At this size B matched the order of cost of Python with the same runtime argument and result checks. At 512 rows the index reduced B lookup time by a factor of 13.9. Plain Python set lookup was about 3.4 times faster than the guarded B call. Exact Int, Text and Bool arguments use the fast scalar path in the B runtime in all rows. The threshold is a backend choice measured on these input types and this hit distribution.
