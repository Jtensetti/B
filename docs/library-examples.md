# Decisions about libraries

A B program can state facts about the libraries it borrows from:

```bee
use py:b_examples.aviation as aviation
foreign aviation.fuel_burn(Duration[h]) -> Volume[gal]
example aviation.fuel_burn(2 h) == 19 gal within 0.001 gal

use py:math as math
example math.hypot(3.0, 4.0) == 5.0
```

An example of an imported function is a decision about a relative's code: *this is the behavior my program relies on*. B type checks it, including units, while compiling. B never runs foreign code during type checking, so the fact is checked where it stands in the program, normally right after the import. If an upgrade changes the library's behavior, the program stops before anything else runs, and the message is written in the example's own unit:

```text
example aviation.fuel_burn(2 h) == 20 gal within 0.001 gal no longer holds: the library returned 19.0 gal
```

`b check FILE --library-examples` runs only these facts, each one separately with only the imports it needs. It reports all of them and exits 1 if any has changed or failed. This is the check to run in CI after a dependency upgrade:

```text
changed: example tariff.vat(100.0) == 25.0
    ... no longer holds: the library returned 12.0
holds: example tariff.vat(0.0) == 0.0
B check: 1 of 2 library example(s) hold
```

The test suite simulates exactly that upgrade: a Python module changes its VAT rate and starts rounding, and the check reports which decision broke.

## Rules

- The name is dotted (`alias.member`). Arguments and the result are literals, and may carry units when the function has a [unit declaration](units.md#across-language-borders).
- `within` gives a tolerance in the same dimension as the result. Without it, results are compared exactly.
- `was` does not apply. It records a change to a B decision. A library's result is whatever the library returns, so the example simply states the new value.
- Every library example appears in the compiler's assumptions as *checked when the program reaches it*. Typing proves nothing about a library's behavior. Only running the example does.

## Limits

- Python only, in practice. The same lowering covers registered .NET methods and npm exports, but neither has been run here: there is no .NET SDK in this environment, and the npm example packages are not installed.
- One call per example, with literal arguments. Properties over many inputs, such as "never negative", and `keeping` for library functions are the next step of [milestone 2](vision.md#milestones).
- A nondeterministic library function needs `within` or should not have examples.
