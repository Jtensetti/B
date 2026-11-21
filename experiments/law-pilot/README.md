# Conditional guarantees and targeted feedback

This controlled pilot asks whether three checker configurations help a model satisfy a new behavior and its proof obligations. The task is a sequencer change that requires passing a transformed pitch to two existing encoders with opposite sign requirements. The starter exposes the numeric range of the calibration, but no conditional sign laws.

## Fixed protocol

Three independent, fresh model contexts receive the same task, starting source and public tests. Each may submit one patch and invoke the checker up to four times. The checks all use B 0.9 with `b check sequencer.bee --require-proofs --json`. The only difference is the additional options:

| Condition | Extra options | Capability |
| --- | --- | --- |
| Ordinary feedback | `--no-conditional-guarantees` | Unconditional interval reasoning |
| Targeted feedback | `--no-conditional-guarantees --explain` | Same reasoning plus guidance on unresolved sites |
| Conditional guarantees | none | Conditional reasoning, ordinary feedback |

The prompt gives the same example of conditional-specification syntax to everyone. The candidate may add laws or a helper that guards the actual calibrated value. No arm starts with the hypothetical fix. Independent source review checks preservation of encoders, calibration and unaffected clients. The oracle exercises all 25 valid pitch steps, rejection outside the input domain and unchanged public helpers. It makes 102 behavior checks, three of which overlap the four public checks. The starter passes 78/102.

Task, scorer, and starting source were frozen before assigning any solver. Their respective SHA-256 values are `6b427ad7757e3458c04f7b3f2367d5478f939fd49f63baeb8d4859c46e1d7773`, `070831adc2eba56e94bef762594460ce38b7a72a857d3f5039f1aa20c993e3a3`, and `70a0ea0ef0b27fa46ccae2309c593d30b1e088b61cf3f52f8224ac6728ec491c`.

The primary outcomes are oracle checks passed and whether the submitted patch meets its assigned proof gate. Secondary observations are checker invocations, changes to contracts, and whether each solver actually receives or uses its extra affordance. Directory isolation is instructional on a shared host. One task and one model context per condition cannot establish a general language advantage. Inference tokens, monetary costs and reasoning compute were not observable.

## Model submissions

| Checker condition | Behavior oracle | Final proofs | Checker calls | Checker JSON bytes, all calls | Final source growth | Final contract growth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ordinary feedback | 102/102 | 5/5 | 2 | 5,366 | 130 bytes | 0 |
| Targeted feedback | 102/102 | 5/5 | 2 | 6,717 | 130 bytes | 0 |
| Conditional guarantees | 102/102 | 6/6 | 1 | 2,587 | 137 bytes | 60 bytes |

All three kept the existing calibration, both encoders, preview and footer behavior. Both controls first tried conditional sign guarantees. Neither disabled checker proved the strengthened postcondition or its two clients. On their next check, the controls submitted byte-identical programs with a helper that receives the calibrated value once and branches on its sign. One control received two suggestions that identified the transformed pitch and the two encoder preconditions. The final condition added two implications to the calibration contract and branched on the requested step. Its first submission passed. The fifth and sixth obligations arise from different submitted programs; proof counts are not independent performance scores.

The enabled run used one fewer checker invocation here. The prompt explicitly taught the conditional syntax and the direct repair matches the two supported rules. The initial prompt did not identify which checker could use those laws. Controls could first see the disabled flag in their first checker response. The observed extra round may therefore reflect learning the checker configuration. A follow-up should disclose available capabilities upfront and counterbalance task wording; another distribution of maintenance tasks could also favor the helper. The table counts serialized checker output and net file growth. Neither quantity measures total model tokens or the cost of authoring guarantees.

The compiler and scorer were frozen for the runs. In the feedback arm, the original suggestion offered both the feasible value guard and a conditional-contract alternative that its disabled checker could not use. The release guidance was subsequently corrected to show only the feasible suggestion in that configuration. See [the recorded check summaries](attempts.json) for actual messages and byte counts. Trial directories were not shared through the solver prompts, and no solver was told the outcome of another arm. The host supplied default model settings without a pinned model identifier.

## Follow-up with capabilities disclosed

Before dispatching three fresh contexts, we locked a single follow-up on the same task, inputs, oracle and four-check budget. The common supplementary instruction said “Ordinary unary integer bounds and guards on the actual value work in all configurations.” A second line disclosed whether conditional contract verification and targeted advice were available in that condition. The solvers received no previous solutions or outcomes. This follow-up used the corrected guidance on a frozen compiler snapshot (Git tree for `b_lang`: `947daf9171be02817a71309d9f24aa2bb5e8c02e`).

| Checker condition | Behavior oracle | Final proofs | Checker calls | Checker JSON bytes | Final source growth | Final contract growth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ordinary feedback | 102/102 | 5/5 | 1 | 2,268 | 130 bytes | 0 |
| Targeted feedback | 102/102 | 5/5 | 1 | 2,284 | 130 bytes | 0 |
| Conditional guarantees | 102/102 | 6/6 | 1 | 2,590 | 140 bytes | 63 bytes |

The earlier difference in checker calls disappeared. Both controls used the same once-evaluated helper as in the original trials. The conditional solver again added two sign laws, this time expressing the bounds as `>= 1` and `<= -1`. No targeted hints were displayed in this follow-up because the first patches already met their proof gates. The stages differ in both capability disclosure and the shared reminder about guards. They cannot distinguish these causes. The observed counts are separate case studies, not pooled treatment estimates. The task permits two effective strategies and demonstrates no stable advantage in model retries. [Recorded follow-up checks and submitted patches](informed-attempts.json).

## Controls from other domains

`cross_domain.py` runs two synthetic cases. Microscopy readout divides by a sample count after a positive input guard. Print layout passes a margin to an inset function with a maximum width after a negative edge guard. Each case has an original implementation, a behavior-preserving rewrite, a withdrawn conditional guarantee with unchanged code, and a defect that violates the original guarantee.

| Source variant | Ordinary checker, consumer proved | Conditional checker, consumer proved | Runtime oracle failures |
| --- | ---: | ---: | --- |
| Original | 0/2 | 2/2 | none |
| Equivalent edit | 0/2 | 2/2 | none |
| Withdrawn law | 0/2 | 0/2 | none |
| Defect | 0/2 | 0/2 | one input per domain |

The oracle covers eight microscopy inputs and nine print-layout inputs per variant. Losing the proof occurred for both the withdrawn law and the actual defect. The failing input was `frames = 1` in microscopy and `edge = -1` in print layout. These curated controls test the rule mechanism and its failure boundary on small programs.

## Replay

From the repository root with the development installation active:

```sh
work=$(mktemp -d)
cp experiments/law-pilot/sequencer.bee "$work/"
patch -d "$work" -p1 < experiments/law-pilot/submissions/ordinary.patch
b check "$work/sequencer.bee" --require-proofs --no-conditional-guarantees --json
python experiments/law-pilot/score.py "$work/sequencer.bee"
python experiments/law-pilot/cross_domain.py
```

Both feedback conditions in both stages submitted `ordinary.patch`. The law-enabled submissions are `conditional-guarantees.patch` in the initial stage and `informed-conditional-guarantees.patch` in the follow-up. Use a fresh working copy for each distinct patch and select its checker options from the table. The scorer accepts any implementation matching the public behavior. Future blinded studies need an unpublished task and oracle.
