# Hidden policies: how many decisions does a program take?

An owner knows a pricing or access policy but has not written it down. B starts from two examples, the first and the last input of the domain. It then asks its own questions, and an oracle answers from the hidden policy. The process stops when B reports the function as settled. The comparison uses the same derivation with examples drawn at random instead of chosen by B.

[check.py](check.py) runs everything. [results.json](results.json) holds the output, and a test re-derives B's side of it.

## Identification

| Policy | Inputs | B questions | B exact | Random, same count: exact share | Random examples until exact (median of 10) |
| --- | ---: | ---: | :---: | ---: | ---: |
| Children free on weekends | 14 | 7 | yes | 0% | 12.5 |
| Age bands: under 12, 65 and over | 100 | 12 | yes | 0% | 40 |
| Shipping: express, weight from 10 | 62 | 13 | yes | 30% | 32.5 |
| Dispatch label by days, 4 bands | 21 | 8 | yes | 25% | 17 |
| Access: admin always, staff 8–17 | 72 | 6 | **no, 81% right** | 0% | 65 |
| 10 kr per item | 10 | refused | — | — | — |

Random examples were scanned one at a time up to 20 and then in steps of 5, so medians above 20 are rounded to that grid. The random learner draws inputs it may already have. It still uses B's derivation, including its preference for the simplest rule. With the same number of examples as B used in total (questions plus two seeds), random examples give the exact policy in at most 30% of trials. To reach the exact policy, random examples need about 1.4 to 2.9 times as many examples as B.

**Where B fails.** The access policy is two cases away from the simplest reading, *everyone but guests*. B settles on that reading after six questions and is wrong for staff outside office hours. The per-item price is not a rule over literals, and B refuses it with `E_EXAMPLE`. That is the intended behavior: write it as code.

## Two mechanisms, switched off one at a time

| Policy | Default | Without neighbor questions | With two extra tests instead of one |
| --- | --- | --- | --- |
| Weekend | 7 questions, exact | 3 questions, 93% right (Sunday only) | 8 questions, exact |
| Age bands | 12, exact | 12, exact | 14, exact |
| Shipping | 13, exact | 13, exact | 20, exact |
| Dispatch | 8, exact | 8, exact | 9, exact |
| Access | 6, 81% | 6, 81% | 17, exact |

Neighbor questions cost four extra questions on the weekend policy and fix it. They cost nothing elsewhere. A wider margin of plausible readings also fixes access, but it needs up to half again as many questions on the other policies and roughly ten times the search time. B ships with the narrower margin, so the access case remains an open problem (vision milestone 2).

## Two changes

| Change | Answers to build | Owner lines for the change | Questions after it | Result |
| --- | ---: | ---: | ---: | --- |
| Children also free on Sundays | 5 | 1, with `was` because B had asked about Sunday | 1 | exact |
| Child rate up to and including 13 | 12 | 2: one new example, one restated with `was` | 0 | exact |

In the second change, the owner's earlier answer `price(12) == 100` contradicts the new policy. The compiler rejects the program until that example is restated as `== 50 was 100`. The simulated owner knows to do that. A real owner would learn it from the error message.

## What this does not show

- **The owner is an oracle.** It answers instantly and correctly. Real owners make mistakes, and the cost of a question to a person was not measured.
- **The policies were written by the author of the mechanism.** They are small and fit the rule language, apart from the per-item case. The two seeds, the first and last domain input, also help B.
- **No model was involved.** The point of B is to reduce a model's work on changes. This experiment only shows that B's choice of questions is more efficient than random examples for the same derivation. Comparing with a model writing Python from the same answers is vision milestone 1.

## Reproduce

```sh
python experiments/decisions/check.py
```

The run takes about three and a half minutes, almost all of it in the random baseline.
