# Which edits does a product owner's rule permit?

A gallery-label designer and a navigation system owner each have four plausible policies. All four allow the installed default. A new implementation then changes that default on different inputs. This deterministic benchmark asks whether clarifying specific alternatives before the change helps decide which revisions to accept. A scripted owner supplies answers from a frozen independent specification. No human or language model was a participant.

## Protocol

| Product | Four candidate policies | Calibration inputs | Held-out inputs |
| --- | --- | --- | --- |
| Label spacing | Exact default, may tighten, may loosen, may do either | Page levels 0 and 1 | Levels 2, 3 and 4 |
| Tab focus | Keep current tab, allow keyboard Home, allow pointer End, allow both | Middle tabs 1 and 2 under keyboard and pointer | Boundary tabs 0 and 3 under both modes |

The product owner, disjoint input partitions, alternative outcomes and all twelve source revisions were fixed before the first comparison. SHA-256 of `cases.py`: `62a4fad4e4b398691a399b5447c36af95080638c8cd5732440eac67fecc4a0e4`. Only the owner oracle sees the hidden rule. Each treatment receives the same four named candidates, the same possible calibration queries, the same facts that current calibration defaults are permitted, and the same two-answer maximum. Each binary question asks whether a single input/output combination is *permitted*. A future implementation may choose a different permitted output.

- **B** calls the production `b_lang.clarification.compare` API on a checked B function. The edit harness compiles and executes each separate B source revision, then tests the survivors' B predicates against the resulting behavior.
- **Typed Python** defines the candidate predicates, split selector and all twelve edits independently. Its integer predicates use ordinary Python functions. The selector balances distinct surviving finite behaviors using the same query budget and ordering as B.
- **Plain language** uses two prewritten yes/no questions per product. A card is skipped when the survivors agree. For example, “With pointer navigation on tab 1, may focus move to tab 3?” The owner answers the exact same membership fact a machine query would express. This compares fixed card choice with active selection. Readability and human effort were not measured.
- **Passive information** receives the same prior facts and asks no questions. With multiple surviving policies, all four methods accept or reject an edit on consensus and otherwise defer. An empty candidate set always defers.

For each product, the six revisions include an equivalent rewrite, two individual behavior changes, a combined change and two alternatives outside the standard suite. Every changed output belongs to the held-out partition. The harness checks B/Python behavioral equality on **all** finite input/output combinations used and agreements on active questions, surviving policies and edit decisions. A source revision is acceptable only if all its held-out outputs are permitted by the independent owner.

## Results

| Scenario | Method | New owner answers | Correct accept | Correct reject | False accept | False block | Deferred |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Four listed rules per product, 48 edit decisions | B / Python / plain language, each | 16 | 18 | 30 | 0 | 0 | 0 |
| Same 48 | Passive | 0 | 8 | 16 | 0 | 0 | 24 |
| Two prior judgments already identify the rule, 12 decisions | All four, each | 0 | 4 | 8 | 0 | 0 | 0 |
| One-answer cap, 12 decisions | B / Python / plain language, each | 2 | 4 | 4 | 0 | 0 | 4 |
| Same 12 | Passive | 0 | 2 | 4 | 0 | 0 | 6 |
| Actual rule omitted, 12 decisions | B / Python / plain language, each | 4 | 2 | 2 | 6 | 2 | 0 |
| Same 12 | Passive | 0 | 2 | 2 | 0 | 2 | 6 |
| Omitted rule with independent contradictory fact, 12 decisions | All four, each | 0 | 0 | 0 | 0 | 0 | 12 |

The columns count judgments about whole code edits. The 48 decisions span eight worlds, with six related edits in each. The 16 answers are two per world. These are deliberately balanced four-policy families, where two well-chosen binary answers suffice to identify a listed rule. The manually written cards achieve the same outcome. The passive strategy safely resolves half of the edits even before any new answers.

In the silent-omission condition, truthful answers leave B with “flexible” for labels and “both edges” for tabs. On the held-out pages, the actual label policy permits the standard default and one special wide fold. Choosing “flexible” therefore accepts a globally tighter edit that the owner rejects and blocks the legitimate wide-fold change. The tab case exhibits both types of error as well. An independent fact that *all* listed policies forbid exposes the incomplete inventory and leaves the decision unresolved. Conditional correctness within a list does not validate that list.

A local microbenchmark on Python 3.12.14 measured a median of **19.578 ms for B and 0.569 ms for typed Python** per 24 matched selector calls across 11 measured batches with alternating order. The B API parses and checks candidate expressions during the call; the Python predicates were predeclared. Initial program compilation, question authoring, owner response time, downstream edits and model costs were excluded. The timing describes these implementations and workloads. This experiment supplies no interaction-quality or total-cost advantage for B over Python or plain language. Machine-checked preconditions and inspectable policy provenance remain distinct reasons to evaluate embedding the interface in B.

## Reproduce

With the B development installation active, run from the repository root:

```sh
python experiments/intent-pilot/run.py
python experiments/intent-pilot/run.py --trace
python experiments/intent-pilot/run.py --timing
mypy --strict experiments/intent-pilot/baseline.py
```

[Recorded decision totals](results.json) are deterministic. The trace prints individual questions and per-edit decisions, including the plain-language card text. Wall-clock timings vary by machine.
