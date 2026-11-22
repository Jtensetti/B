# Questions about permitted behavior in B 0.11

A layout function currently returns a gap of 1 at rank 0. A contributor proposes returning 2. Four possible requirements agree with every current output, but differ about which future outputs are permitted. Put those alternatives in a [request file](../examples/intent/layout.json) and ask B about the actual edit.

```sh
b clarify examples/intent/layout.bee examples/intent/layout.json --edit examples/intent/compact.bee
b clarify examples/intent/layout.bee examples/intent/layout.json --edit examples/intent/compact.bee \
  --answer '{"inputs":{"rank":0},"result":2,"allowed":true}' --json
```

The first call asks “May gap(rank=0) return 2?” The owner can allow the change while leaving unresolved whether rank 2 may use a wider gap. The second call returns `approve` with two named policies still possible. Those policies admit all three revised returns. With a negative answer the decision is `reject`. A null answer says the owner cannot decide that cell and leaves this edit `inconclusive`.

## Request and evidence

The request names a B function, two to sixteen named Boolean postcondition expressions, explicit input axes keyed by parameter name, and a list of integer outputs. Each expression refers to parameters and `result`. Supply trusted answers in the optional `answers` array, using the same objects as `--answer`. The source and response files are read-only. If different people or versions use a different meaning of “allowed”, start with the corresponding requirements and answers.

Each response is a judgment that the result is permitted or forbidden at the given input, or an abstention (`null`). Observing one actual result says nothing about the permissibility of alternatives. The base function's `requires` filters the input grid. Ordinary comparison uses neither its body nor its existing `ensures` to choose the requirement. The caller supplies the candidates. A true rule missing from that list can yield consistent answers and a wrong selection.

### Choosing a policy

```sh
b clarify examples/intent/layout.bee examples/intent/layout.json --strategy minimax --json
```

The default `balanced` strategy counts distinct behaviors on the grid, so copying a clause under a second name gives it no additional vote. It selects a question whose smaller answer group is largest, breaking ties in favor of small absolute input and output values. `minimax` considers subsequent questions as well, minimizing the worst-case number of additional definite answers. This guarantee assumes truthful binary answers, equal cost per answer, a listed true policy and the declared finite grid. The exact planner handles at most ten observable classes and 32 distinct nontrivial partitions. Larger cases fall back to balanced selection and record the reason. A nine-policy example needs five questions with the default heuristic and four with exact planning. [Mechanism and independent oracle](../experiments/intent-limits/README.md).

| Identification status | Meaning |
| --- | --- |
| `question` | The report contains an input, a hypothetical output, and the policies on each side. |
| `selected` | One named policy remains consistent with the supplied answers. |
| `equivalent-on-grid` | Several names remain and give identical answers on every admissible cell. They may differ elsewhere. |
| `undetermined` | Distinct behaviors remain, but all available separating questions were skipped. |
| `inconsistent` | No listed policy fits the answers. The catalog may be incomplete or the evidence contradictory. |
| `empty-domain` | There are no admissible input/output cells on this grid. |

A later definite answer to a skipped cell can resolve it. Opposite definite answers to one cell cause inconsistency. Terminal information includes surviving policies, equivalence classes, the grid and counts of definite and skipped answers. The report with `--strategy minimax` distinguishes the depth for identifiable behaviors from the depth for all remaining behaviors if skipped cells make full identification impossible.

### Deciding a specific edit

`--edit FILE` evaluates the revised target using B's bounded native integer interpreter, including nested calls and runtime contracts. B checks its signature and entry domain against the original on the supplied inputs. A revised body that fails to return a supported value, a changed domain on the grid, or an output outside the supplied list yields `inconclusive`. B never runs arbitrary top-level statements or foreign functions for this analysis. Ordinary compilation and Python metadata resolution still use their usual trusted tooling.

| Edit status | Meaning for the revised target's outputs | Exit |
| --- | --- | ---: |
| `approve` | Every surviving policy permits every revised normal result on the grid. | 0 |
| `reject` | Each surviving policy forbids at least one revised result. | 1 |
| `needs-answer` | The policies disagree about the edit. The question uses an actual revised result. | 2 |
| `inconclusive` | The comparison lacks sufficient evidence. See the reason and witness, when available. | 2 |

The JSON includes the verdict under each surviving policy and witnesses for rejection. Approval concerns current target returns. Exception behavior outside the grid, other functions, performance, cross-call relationships and the compatibility of future implementations with a newly tightened declaration require separate evidence. `b check --require-proofs` continues to check declared B obligations. Plain identification exits 0 on a normal question, selection or equivalence. It exits 2 on inconsistency, an empty domain, unanswered remaining distinctions or invalid input.

### Bounds

The core supports exact integer parameters and result, comparisons, Boolean logic and bounded integer arithmetic. It admits at most eight parameters, 256 listed values per axis, 4,096 requested cells or input rows, and a bounded expression-evaluation budget. Edit observation uses the existing smaller native interpreter fragment, including at most four parameters and 128-bit observed integers. Errors and budget exhaustion cannot produce an approval.

## What changed in practice

- In a [matched B, typed Python and plain-language study](../experiments/intent-pilot/README.md), all three active approaches classified 48/48 held-out edit decisions when the owner's rule appeared in the list. Omitting the true rule induced six false approvals and two false blocks per method in twelve decisions. The study used a scripted owner.
- In a [separate edit-decision comparison](../experiments/edit-questions/README.md), deciding each edit directly took 14 answers across sixteen isolated decisions, compared with 32 for full identification. When earlier answers were retained across a sequence of edits, both methods used eight.
- A [complete finite layout experiment](../experiments/layout-coherence/README.md) exhibits two requirements with identical one-row permissions and different judgments about the whole screen. A question about two rows separated them. The joint-question search is an experimental reference implementation.

Directed example questions have a history in programming by example, and identifying the best decision before fully identifying a hypothesis is an established active-learning problem. B exposes these distinctions to a caller operating on a typed program and a proposed revision. [Mayer et al., UIST 2015](https://www.microsoft.com/en-us/research/publication/user-interaction-models-disambiguation-programming-example/) · [Golovin, Krause and Ray, NeurIPS 2010](https://proceedings.neurips.cc/paper_files/paper/2010/file/1e6e0a04d20f50967c64dac2d639a577-Paper.pdf).
