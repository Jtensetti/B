# Unit mistakes at a language border

[plan.bee](plan.bee) and [plan.py](plan.py) compute the same flight plan with two Python libraries that work in knots, pounds, feet, gallons and degrees Celsius ([aviation](../../b_examples/aviation.py), [weather](../../b_examples/weather.py)). The B version declares the libraries' units once. The Python version converts by hand with named constants and type hints. Both print the same three numbers.

[check.py](check.py) applies seven one-edit mistakes to each version and runs it. [results.json](results.json) holds the outcome.

| Mistake | B | Typed Python |
| --- | --- | --- |
| Speed and weight swapped | rejected before running | wrong result, no error |
| km/h passed where the library expects knots | rejected before running | wrong result, no error |
| kg passed where the library expects pounds | rejected before running | wrong result, no error |
| Meters passed where the library expects feet | rejected before running | wrong result, no error |
| A result in feet used as meters | rejected before running | wrong result, no error |
| Gallons added to liters | rejected before running | wrong result, no error |
| Minutes passed where the library expects hours | wrong result, no error | wrong result, no error |

Both versions have 12 nonblank lines. The B version spends three of them on unit declarations, and the Python version spends four on conversion constants. For this program, milestone 1's kill criterion is not met: the annotations cost no extra lines, and they prevent six of the seven mistakes.

B misses the last mistake for a structural reason. `95 h` is a perfectly good duration, so writing the wrong number in the right dimension cannot be a type error. Only an example or a check of the result would catch it.

## A bug this experiment found

The first B run printed 12.0 liters of fuel, where Python printed 68.9. B's compile-time folding of exact quantities, added in 0.22, looked values up by Python object identity (`id()`). Python reuses identities once objects are freed, so the library call's result was mistaken for an unrelated literal. The fix keeps a reference to each folded node and checks identity on every lookup. A regression test builds forty such expressions.

## What this does not show

- **The mistakes were chosen by the author of the mechanism.** They are typical, but no model or person made them.
- **The baseline is the weakest one.** Typed Python without a unit library has no unit protection at all. Python with [pint](https://pint.readthedocs.io/) would catch dimension mismatches *when the code runs*, but not before. Its calls into these libraries would still need manual `.to("knot").magnitude` conversions. pint could not be installed here, so that comparison was not run.
- **One program.** A larger program with more libraries, and mistakes made by a model, is part of the journey trial (milestone 5).

## Reproduce

```sh
python experiments/border-units/check.py
```
