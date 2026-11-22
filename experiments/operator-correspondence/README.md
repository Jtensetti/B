# When does the same operator mean the same thing?

This experiment asks whether a recurring correspondence across examples helps identify an operation's meaning. Comparative linguistics uses regular correspondences to investigate relationships beyond surface resemblance. Here the target is observable program behavior on a specified domain. The probe makes no claim about historical ancestry and its observations never become compiler guarantees. [Campbell, *Historical Linguistics*, comparative method](https://www.igntu.ac.in/eContent/MA-Linguistics-02Sem-Dr.%20Anusree%20Sreenivasan-Historical%20Linguistics.pdf)

We ran integer remainder in B, Python and C# over all 300 pairs with dividend from −12 to 12 and nonzero divisor from −6 to 6. We compared each output with three candidate conventions: floor division, division truncated toward zero, and Euclidean remainder in the range from zero up to the divisor's absolute value, exclusive. The domain fits C# Int32. B runs on CPython, so agreement between B and Python is expected.

| Input set | B and C# agree on remainder | Candidate conventions still possible for each language |
| --- | ---: | --- |
| Both operands positive | 72/72 | All three |
| Positive pairs plus (−5, 4) and (5, −4) | 72/74 | B and Python use floor, C# uses truncation |
| Entire signed grid | 214/300 | Same identification within this candidate set |

A second procedure chooses the next input by minimizing the largest number of candidate rules that could survive the observation. It has access to predictions and the range of allowed inputs; it reads a stored runtime result only after selecting that input. For each runtime it chose (−1, −2) and then (−1, 2). The first result was −1 in all three and eliminated the Euclidean convention. The second was +1 in Python and B, and −1 in C#. Two selected observations distinguished all candidates still in play. An unlisted convention could still agree on these cases.

We tested this weakness with a real fourth operation, Python's IEEE-style `math.remainder`, while keeping the original catalog of three hypotheses frozen. It answered both chosen queries exactly like C# integer remainder. The selector returned truncation. On the 298 unqueried pairs, that prediction failed 80 times. For example, at (3, 4) truncation gives 3 while IEEE-style remainder gives −1. This control compares numeric values on small exactly representable inputs. It does not assert that the operations have identical types or signed-zero behavior. [Python math.remainder](https://docs.python.org/3/library/math.html#math.remainder)

A positive control used three syntactically different ways to return the sign of the dividend. They agreed in all 300 rows (25 distinct dividends). A single mismatch rules out unconditional equivalence; any universal replacement needs a shared specification and suitable bounds, including representation and exception behavior. The Python and C# references confirm the distinct integer remainder sign conventions. [Python expressions](https://docs.python.org/3/reference/expressions.html#binary-arithmetic-operations) · [C# arithmetic operators](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/operators/arithmetic-operators#integer-remainder)

## Reproduce

Install B from the checkout and put a .NET 10 SDK on PATH. From the repository root run:

```sh
python experiments/operator-correspondence/compare.py
```

The script executes compiled B and a C# file-based application, compares the observations with independently defined candidate rules and prints JSON. No external package or network service supplies the expected outputs.
