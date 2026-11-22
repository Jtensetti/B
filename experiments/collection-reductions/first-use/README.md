# First use on a collection of records

Two fresh contexts received the [same weighing task](TASK.md). One wrote [B](ledger.bee) with a short B syntax reference covering functions, nullable keys and reducers. One wrote [typed Python](ledger.py) with the standard library available. Each had one submission, could read only the task, and had no compiler, execution or test feedback. Neither saw the independently written [scorer](check.py). The requested public inputs are already well-typed. The scoring covers incomplete records, exact thresholds, zeros, negative and very large integers, and irrelevant keys.

| Submission | Initial result | Same source on the revised grammar |
| --- | --- | --- |
| B | Parser rejected a newline directly after the first function's equals sign, before any case could run | 2,340 of 2,340 |
| Typed Python | 2,340 of 2,340 | 2,340 of 2,340 |

The B submission split four declarations after their equals signs. At that location a function always needs its body, so allowing line breaks produced an unambiguous continuation. B 0.16 accepts it for both functions and let bindings. The submitted B and Python files were kept intact. The revised score is a replay after modifying the compiler. A new blind task would measure first-attempt performance with the revised language. Many cases test one implementation of one task per language.

```sh
python experiments/collection-reductions/first-use/check.py
```
