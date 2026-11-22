# Does discovering a contract help a model specify the intended behavior?

Two independently specified maintenance tasks test the distinction between proving a property of current code and choosing a public contract. The ledger has a latent arithmetic bug. The spacing implementation already conforms to its policy, which permits multiple alternative defaults. In each task, the mechanism can discover an exact law that describes the starter.

## Frozen protocol

Two new solver contexts per task and condition receive the identical source, product intent, common task instructions and public examples. One upfront line truthfully discloses the availability of candidate discovery. Both sides are told that a proof relates a claim to an implementation, with intent supplied separately. Everyone runs the same initial inspection before editing. In the enabled condition inspection additionally runs `b discover`. Both arms then have at most three further instrument calls. They may check their patch or, in the enabled condition, repeat discovery. We count each CLI invocation separately, including the mandatory extra discovery call. The discovery arm incurs the cost of reading its proposals even if it ignores them.

The independent scorer was frozen before any solver was assigned. Its SHA-256 is `707fb533e04c8e1b5d7462fe3a61f810aa65092cab572807aa4e0d4fec5d111e`; the common task digest is `53994c18160e10d434b3e5926819d71dd52304e839892ea0403106e6812b8a75`. Two weak public examples per task verify output and an unaffected function. They deliberately cannot distinguish either tempting exact rule from the policy.

For the ledger, the scorer exhausts 49 valid input pairs. For spacing, it exhausts seven ranks. Against each input it evaluates the declared clause on 27 candidate outputs, including every permitted result, near-boundary values and two outliers. A **blocked legal** output excludes a conforming implementation. An **admitted illegal** output would let a nonconforming implementation satisfy the public rule on that input. The default-output oracle is separate to catch unwanted changes by the current engine. The scorer also checks static proof of the published postcondition, a small set of invalid inputs and the unaffected footer. The finite checks do not quantify over all integer outputs.

Solvers use separate working directories on a shared host with instructional isolation. Each receives a fresh context under the same default model settings, without a pinned model build. A context never receives another submission or the scorer. The closed specifications are supplied in full in natural language; the unseen measurements test interpretation, not access to hidden product requirements. We record serialized output bytes and instrument calls. Model-token usage, elapsed inference compute and total cost are unobserved.

## Model outcomes

| Task | Discovery | Policy-correct submissions | Default behavior | Blocked legal / admitted illegal | Instrument rounds per solver | Total report bytes per solver |
| --- | --- | ---: | --- | --- | --- | --- |
| Ledger | Off | 2/2 | 49/49 each | 0 / 0 | 2, 2 | 1,468; 1,468 |
| Ledger | On | 2/2 | 49/49 each | 0 / 0 | 2, 2 | 1,936; 1,936 |
| Spacing | Off | 2/2 | 7/7 each | 0 / 0 | 2, 2 | 1,528; 1,528 |
| Spacing | On | 2/2 | 7/7 each | 0 / 0 | 2, 2 | 2,008; 1,975 |

Every solver inspected once, edited the program, and passed on its first subsequent check. All submissions preserved the public domain and footer, and all eight published postconditions were proved. Each enabled solver actually received its starter's proposed contract with current-code verification marked `proved`. None published that misleading formula. Neither enabled solver working on spacing changed the conforming default.

Each ordinary run made two static CLI calls and one public-oracle call. Each enabled run also made one discovery CLI call. Instrument rounds count interactions with the wrapper; total bytes include serialized machine reports and public test output. Code and policy access were shared between arms. Once both are short and explicit, the ordinary checker and the model already suffice on these tasks. The results show a ceiling on solver accuracy and extra information delivered; they supply no inference-token or total-cost advantage. [Run-level observations and submitted patch names](results.json).

## Negative controls

Running discovery on the unmodified ledger observed nine values and proposed `result == arrivals + departures + 1`. The affine verifier proved the formula for the actual implementation. Copying that clause without repairing the code retains the wrong default on 42/49 input pairs. It also blocks the legal result on those same 42 inputs and admits an illegal result for each.

For spacing, four observations yielded `result == rank + 1`, also proved against the current implementation. Copying it passes all seven default-output checks while blocking 34 of the 41 permitted rank/gap combinations. Neither of these failures is detectable by proof against the current implementation alone. To reproduce the seeded controls, run `python experiments/contract-pilot/controls.py` with this revision installed.

A preflight uncovered a sampling issue on small bounded input domains. The initial picker kept every unused point in its discovery pool out of its challenge pool. Both starters consequently produced a single survivor without a held-out challenge. The implementation now sets aside admissible challenges before observing outputs. The experiment used the corrected compiler for all arms ([frozen compiler and pre-trial protocol](https://github.com/Jtensetti/B/tree/01af14f6b7676f84a15ecb0d0fb8dd5a65b19441), `b_lang` tree `fda8a047da7527cb3c38e49229a60630fcc5df69`). The wrapper exposed the standard checker and candidate discovery only; explicit expected-law and trace options were outside this trial.


## Does the compiler need to sample an affine function?

A separate engineering comparison asks the symbolic checker to return its normalized body formula directly, with no observations. On the booking example and both pilot starters it returns the same three verified formulas. The observation-first path spends 14, 9 and 4 observations respectively. For `2*x` the direct path also derives the formula, while discovery eliminates every member of its template family.

Two piecewise controls show where the approaches differ. An exceptional result at 10007 leaves the symbolic path without a single affine formula. The observational path proposes identity after ten samples, and verification correctly stays unknown. Moving the exception to 17 produces a counterexample to a declared identity at input 17, where the body returns 18. The direct path still has no single formula. These six selected cases isolate mechanism differences. They measure neither real-world incidence nor model impact.

```sh
python experiments/contract-pilot/compare_inference.py
```

## Replay

With the revision installed, run from the repository root:

```sh
trial=experiments/contract-pilot
work=$(mktemp -d)
cp "$trial/ledger/program.bee" "$work/program.bee"
patch -d "$work" -p1 < "$trial/submissions/ledger-1.patch"
b check "$work/program.bee" --require-proofs --json
python "$trial/score.py" ledger "$work/program.bee"
python "$trial/controls.py"
```

Use a fresh directory, the matching starter and the patch named in `results.json` to replay another submission. Python and B package versions can change the shape and byte count of the CLI report; recorded bytes refer to the frozen trial build.
