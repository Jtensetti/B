# Conditional integer guarantees

B 0.9 can prove an integer result bound for a particular input range and reuse it in another function. The contract is part of the public interface. This example describes an ideal discrete flight with upward velocity three at tick zero and a velocity change of minus one per tick.

```bee
fn velocity(t: Int) -> Int pure requires t >= 0 ensures (t <= 3 or result < 0) and (t >= 3 or result > 0) and (t != 3 or result == 0) = 3 - t
fn descent_speed(t: Int) -> Int pure requires t > 3 ensures result > 0 = -velocity(t)
fn time_per_unit(t: Int) -> Float pure requires t > 3 = 1 / descent_speed(t)
```

Here `t <= 3 or result < 0` says that a tick greater than three implies a negative result. The caller can establish that condition. Negating the velocity gives a positive speed, and a downstream reciprocal has a nonzero divisor. The conditions also describe ascent and the instant of zero velocity at the top.

```sh
b check examples/mechanics/flight.bee --strict --require-proofs --json
b check examples/mechanics/flight.bee --no-conditional-guarantees --require-proofs --explain
b impact examples/mechanics/flight.bee examples/mechanics/rebound.bee
```

The second command disables the new analysis on the same compiler and exits with a proof error. The rebound fixture introduces a collision at tick five while retaining the old contract. Impact reports three lost proofs. Calling `velocity(5)` in that revision raises a postcondition error. This exact witness is supplied by a test; an `unknown` status on its own would not identify it. The first four transitions of the two models agree.

## What the checker accepts

The result and the parameter used by a rule are both `Int`. A rule takes the form `guard or conclusion`. The guard compares a single parameter with an integer literal. The conclusion compares `result` with an integer literal and must yield an interval or the fact that the result is nonzero. Either operand order is allowed in these comparisons. Contracts can conjoin ordinary bounds and up to eight such rules. If there are more, the existing interval checker is used. These limits bound the extra case analysis for each function.

To establish a rule the checker can analyze the body with the guard assumed false and check the conclusion under that restriction. Each rule is handled separately. Every conjunct of the contract must hold before the conditional information becomes available at call sites. Calls still need to satisfy the producer's precondition. Foreign signatures, names and examples cannot certify a result bound. Proofs concern calls that return normally.

The JSON `proof_method` can identify participation of a conditional guarantee. The on/off comparison measures whether it changes the outcome for a particular program. A route the verifier used need not be the only possible route. Changing the analysis flag never removes a runtime contract.

## Where the analysis stops

Suppose an identity function explicitly promises that positive inputs yield positive results and negative inputs yield negative results. Both guarantees can be checked. A caller may still know only that its input is nonzero. Neither sign is known, so the current transfer cannot select either guarantee and leaves the divisor open. The single clause `x == 0 or result != 0` proves exactly what that caller needs. This difference raises a practical question about the cost of choosing and maintaining contracts.

`b check --explain` offers site-specific advice on open divisor checks and simple integer argument bounds. It distinguishes testing the producer's input from validating the actual value passed to the consumer. Applications supply the behavior outside the allowed range. Advice has no effect on the proof status.

## A conservation law the checker cannot establish

Booking one place reduces the number of free places by one and increases the booked count by one. We encoded the proposed accounting invariant, `result == free + booked`, in [a runnable example](../examples/conservation.bee). Both functions satisfy their local sign contracts even in a faulty revision which adds two bookings for every place removed. The conservation requirement remains statically open in both programs. Across 100 starting states the correct transfer conserved the total in every case; the faulty transfer created one extra place each time and its runtime postcondition failed. Run `pytest -q tests/test_conditional_guarantees.py -k conservation` to reproduce both observations.

This example would require a relationship between several quantities across function boundaries. Knowing their separate signs is insufficient.

## Experiments

- [AI maintenance task and cross-domain controls](../experiments/law-pilot/README.md)
- [An operator correspondence experiment across B, Python and C#](../experiments/operator-correspondence/README.md)

The mechanics example draws on qualitative reasoning about changes of state. Reasoning about sign before magnitude also has a long history in static analysis. See [Qualitative Process Theory](https://dspace.mit.edu/entities/publication/a48814a2-9d2b-4694-9e7a-0d5b3b019d7f) and [Cousot and Cousot on abstract interpretation](https://www.di.ens.fr/~cousot/COUSOTpapers/POPL77.shtml).
