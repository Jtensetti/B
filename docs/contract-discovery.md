# Discovering and checking a contract in B 0.10

A reservation moves one place from free to booked. A model maintaining the system may want to know whether this preserves their sum. The following commands answer two different questions about the same operation.

```sh
b discover examples/conservation.bee --function accounted --expect 'result == free + booked' --json
b check examples/conservation-modular.bee --strict --require-proofs
```

The first command inspects the current helper bodies. Fourteen observations in this example leave one candidate, `ensures result == free + booked`. A separate symbolic pass proves the equation using `booked_after` and `free_after`. Removing the target's own `ensures` still yields the same proposal. The caller-supplied expectation is checked separately and can disagree with the proposal.

The second command checks a [version with explicit helper contracts](../examples/conservation-modular.bee). A helper guarantees `result == free - 1` and the other guarantees `result == booked + 1`. The compiler substitutes these independently verified equations at the two calls. Keeping only the helpers' sign guarantees leaves the modular conservation proof open. A discovery result never publishes an interface or edits source.

## What each result means

| Report field | Interpretation |
| --- | --- |
| `status` | `candidate` means one member of the search family survived. `ambiguous` means several survived. `no-match` means all were eliminated. `unsupported` or `inconclusive` gives the reason the search could not finish. |
| `verification` | A separate symbolic pass over native BIR checked a proposed formula against the function body. `proved` applies to that implementation on its entry domain when the body produces a value. `unknown` leaves the formula unproved. |
| `declared_audit` | Reports whether the existing target postcondition was present, supported, checked on observations, or contradicted. `declared_counterexample` records the first witnessed failure. `no-observed-violation` describes the samples only. |
| `expectation` | Present with `--expect`. A proved expectation matches the symbolic result. A refuted expectation includes inputs, predicted result and actual body result. Other cases are unknown. |
| `proposal_origin`, `intent` | A candidate describes this implementation. Choosing an interface that future implementations must satisfy requires independent requirements. |

Discovery observes the target's body result immediately before its own runtime postcondition check. An ordinary public call on that input may raise a contract error. Nested calls keep their pre- and postcondition checks during observation. No top-level B statements or foreign functions are executed by the observer. File loading uses the usual static checker and its trusted Python import hooks. Source that fails the front end returns a compilation diagnostic.

Use `--trace` for all observations, surviving candidates, elimination counts and example counterexamples. Discovery alone exits successfully when it produces a report, including an inconclusive one. With `--expect`, success requires a symbolic proof of the supplied equality. A refutation, an unknown expectation and rejected input each produce a nonzero exit.

## Where the two analyses run out of evidence

The search accepts pure native functions of up to four integer inputs with integer results. It tries a constant, one- or two-input formulas with coefficients of magnitude one and offsets of −1, 0 or 1, and a sum of all inputs for larger arities. It picks distinguishing inputs from a bounded pool. Up to eight observations select candidates and up to twelve additional probes challenge them. These deterministic held-out points can miss a branch. A proposal that passes the probes can therefore still have an unknown verification result.

The symbolic pass normalizes additions, subtractions and multiplication by an integer constant. It can verify a supplied equation such as `result == 2 * x` even when discovery finds no candidate. Certain branches can be proved when they yield the same form or a condition restricts execution to one branch. Variable products, general piecewise formulas, unproved call preconditions and analysis-budget exhaustion can all leave a proof open. Both kinds of proof concern values on normal completion. An implementation can still raise or lack any admissible input. The checker is part of the trusted codebase.

## When a proven formula makes a bad requirement

Giving two places to a booking that removes one free place makes the sum rise by one. B can prove that erroneous formula for the changed code. Supplying the conservation expectation separately produces a concrete disagreement. A second failure is subtler. A layout engine implements one permitted default per rank, while the product specification permits several choices. Publishing its exact current behavior excludes 34 of the 41 legal rank/gap combinations. See the [pilot, negative controls and independent scoring rules](../experiments/contract-pilot/README.md).

There are precedents for pairing inferred properties with static checking and for scoring model-generated postconditions against faulty implementations. The B experiment asks whether displaying the result helps a model preserve both the intended restrictions and the freedom of future implementations. [Nimmer and Ernst, FSE 2002](https://homes.cs.washington.edu/~mernst/pubs/annotation-study-fse2002-abstract.html) · [Endres et al., FSE 2024](https://www.microsoft.com/en-us/research/publication/formalizing-natural-language-intent-into-program-specifications-via-large-language-models/).
