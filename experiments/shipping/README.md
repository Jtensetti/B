# The shipping trial: a task where B has nothing to borrow

The [journey trial](../journey/README.md) favored B because its semantics lived in an npm library that Python had to reimplement. This second trial removes that advantage on purpose. It also uses a smaller model, so that mistakes become more likely and the error criterion can separate the languages.

## Design

- **Task.** A quote calculator in five steps ([steps](steps/)). It reads orders and a catalog as JSON. It quotes every parcel with a carrier library that works in pounds and US dollars ([carrier.py](workspace/carrier.py)). Later steps add fuzzy product names, Swedish kronor, dimensional weight from liters and cubic inches, and express shipping. The conversions are traps: a pound is defined as exactly 0.45359237 kg, and the carrier rounds the weight up to whole pounds, so multiplying by 2.20462 instead of dividing gives a wrong price for exactly one pound.
- **Libraries.** Python's standard library and the carrier module, which sits beside the program in both languages. The npm package `fastest-levenshtein` is available to both.
- **Solvers.** Four instances of Claude Haiku, two per language, each in its own workspace, with the same instructions as in the journey trial. B solvers learned B from its documentation.
- **Hidden tests.** 15 fixtures, including exactly one pound, zero quantity, fuzzy-match ties, a dimension-dominated parcel, express flags and rounding to öre. Numbers may differ by less than 0.001.

## Results

**Correctness.** All four solvers passed all 15 fixtures at all five steps ([grades](results/grades.txt)). Haiku made no errors that the hidden tests caught, in either language. Every solver tested its own work. The B solvers compared their programs with Python references they wrote themselves, on 50–300 random cases per step.

**Work** ([per step](results/work.json)):

| Solver | Output tokens: build | Output tokens: 4 changes | Output tokens: total | Tool calls | Seconds | Program |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B 1 | 40,214 | 52,294 | 92,508 | 35 | 348 | 48 lines |
| B 2 | 46,835 | 54,194 | 101,029 | 42 | 418 | 41 lines |
| Python 1 | 5,645 | 22,903 | 28,548 | 21 | 45 | 83 lines |
| Python 2 | 5,872 | 19,674 | 25,546 | 19 | 44 | 95 lines |

**B lost clearly.** It took about 3.6 times the output tokens and 8 times the wall time, with equal correctness.

- **The build cost** is mostly learning B: reading the documentation and trying out syntax. There was no library to borrow that Python lacked.
- **Each change** still cost B about 2.4 times as much as Python. The B solvers kept writing randomized Python references to check their B programs. In effect they used Python as the trusted language and B as the one under suspicion.
- **Neither B solver used units**, even though the task is a unit conversion problem and the B documentation describes `Mass[lb]` at a foreign border. Both wrote the same arithmetic as the Python solvers. Neither used `example` either. B's distinctive grammar went unused, so it could not prevent anything.
- **Friction reported by a solver:** a newline before `else` is rejected outside parentheses.

## What the two trials say together

| | Journey (npm semantics) | Shipping (Python library) |
| --- | --- | --- |
| Errors, B vs Python | 0 vs 0 | 0 vs 0 |
| Total output tokens, B ÷ Python | about 0.55 | about 3.6 |
| Output tokens per change, B ÷ Python | about 1.8 | about 2.4 |

B pays off when a sibling language's library replaces hundreds of lines of reimplementation. Otherwise B is more expensive, because a model must learn it and does not yet trust it. Neither trial showed fewer errors. Two strong-enough models reached the ceiling in both languages, including the smaller one. The long-term goal is therefore **not met**: B has not been shown to produce fewer errors. It produces less total work only when borrowing across ecosystems is the bulk of the task.

## Limits

- Two solvers per language and two tasks, all designed by B's author.
- The solvers were not told about B's units or examples specifically. They were pointed at the same documentation as everything else. A trial that names the features would test them, but it would no longer be a neutral comparison.

## Reproduce

```sh
python experiments/shipping/oracle.py experiments/shipping/fixtures
JOURNEY_FIXTURES=experiments/shipping/fixtures python experiments/shipping/grade.py 5 path/to/workspace -v
```
