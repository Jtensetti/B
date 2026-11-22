# Surface spelling and recoverable shorthand

We encoded each of the 27 B source files under `examples/` at commit `02cd226` separately. Quoted strings retain their exact contents. One transformation deletes ASCII vowels including Y from identifiers and keywords. The other replaces each of 24 keywords with a distinct rune. We checked that the rune mapping round-trips on this corpus. The vowel mapping has collisions, including `as` and `use`.

| Input | o200k_base | cl100k_base |
| --- | ---: | ---: |
| Ordinary B source | 1,636 | 1,627 |
| Remove vowels outside quoted strings | 2,007 | 2,015 |
| One rune per keyword | 2,215 | 2,087 |

The compact handoff format uses a different principle. It can recover the comparison operator and, on single-parameter functions, the name of the parameter from the operation and the compiler's symbol table.

| One line including its final newline | o200k_base | cl100k_base |
| --- | ---: | ---: |
| `next route when days == 5 => "express"` | 11 | 11 |
| `route 5 "express"` | 6 | 6 |
| `next signal when phase == 3 => 8` | 11 | 11 |
| `signal phase 3 8` | 7 | 7 |

The counts exclude teaching the format, reading the target signatures and recovering from invalid submissions. The [generation pilot](../shorthand-pilot/README.md) examines those costs for a small pair of product requests.

The measurement is a Node script with an optional tokenizer dependency. A full Git checkout is needed for the pinned source corpus. To reproduce with gpt-tokenizer 4.1.2 from the repository root:

```sh
work=$(mktemp -d)
npm install --prefix "$work" --ignore-scripts --no-audit --no-fund gpt-tokenizer@4.1.2
node experiments/shorthand-encoding/measure.mjs "$work/node_modules/gpt-tokenizer/esm/encoding/o200k_base.js"
node experiments/shorthand-encoding/measure.mjs "$work/node_modules/gpt-tokenizer/esm/encoding/cl100k_base.js"
```
