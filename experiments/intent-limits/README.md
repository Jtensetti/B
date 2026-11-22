# The most balanced question can cost an extra round

One reviewer knows which of nine policies governs the permitted integer results for input `x = 0`. Every answer is accurate, the true policy is in the catalog, and every pair of policies differs on at least one of the five test results. Each yes/no question costs one round. The objective is to identify **any** of the nine policies within the smallest possible worst-case number of rounds.

The fixture was selected to challenge the greedy rule. Its nine sets of permitted results are recorded in [measure.py](measure.py). The script uses B's balanced and minimax selectors to interview each possible reviewer. A separate exhaustive search computes the smallest worst-case depth by trying every useful question at each possible set of remaining policies. The production selectors and the independent reference search have exactly the same five questions available.

| Result in the first question | Policies allowing it | Policies forbidding it | Worst-case rounds, including this first question, if later choices are optimal |
| ---: | ---: | ---: | ---: |
| 0 | 7 | 2 | 4 |
| 1 | 5 | 4 | 5 |
| 2 | 3 | 6 | 4 |
| 3 | 3 | 6 | 4 |
| 4 | 3 | 6 | 4 |

The uniquely most balanced first question asks whether result 1 is allowed. Within the five policies that allow it, policy B permits exactly results 0 and 1. Each of the four competing policies differs from B on a different single result. The reviewer who chose B must therefore answer four more questions after answering the first. With the balanced strategy, seven of the nine reviewers finished within four rounds. Policies B and D each took five. The optional minimax planner began with result 2 and identified all nine policies within four rounds. A depth of three could distinguish at most eight policies, so four is optimal.

This case isolates the difference between minimizing the largest group after one answer and minimizing the length of the entire interview. The frequency of this pattern in real policy work and the effort of answering a question remain unmeasured.

An editable installation of B 0.11 can replay every interview and regenerate the table.

```sh
python experiments/intent-limits/measure.py
```

The underlying research problem has a longer history. Mitchell describes maintaining the set of hypotheses compatible with observations. Angluin distinguishes membership questions from queries about equivalence to a complete specification. Nowak analyzes balanced-split generalized binary search and identifies conditions for its query-complexity guarantees. Directed example questions have also been studied for resolving user intent in programming by example. [Mitchell (1977)](https://ijcai.org/proceedings/1977/68), [Angluin (1988)](https://doi.org/10.1007/BF00116828), [Nowak](https://arxiv.org/abs/0910.4397), [User Interaction Models for Disambiguation in Programming by Example (2015)](https://www.microsoft.com/en-us/research/publication/user-interaction-models-disambiguation-programming-example/).
