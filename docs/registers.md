# Writing a decision in two registers

A parcel's lead time determines its route. In a table, changing the cutoff for priority parcels takes one row.

```bee
fn route(days: Int) -> Text pure = cases days {
    < 0 => "overdue"
    == 0 => "today"
    <= 3 => "priority"
    else => "standard"
}
```

The same decision in ordinary B reads as follows.

```bee
fn route(days: Int) -> Text pure = if days < 0 then "overdue" else if days == 0 then "today" else if days <= 3 then "priority" else "standard"
```

Rows are checked from the top. At zero days both `== 0` and `<= 3` match. The earlier row returns `"today"`. The last row must be `else`. Branches may contain any B expression, including formulas, calls and further tables. The compiler type-checks every branch. At runtime it evaluates only the selected result. B supports the usual six comparison operators on the same types accepted in an ordinary comparison. The left operand is one name. The right operand is a number, string, boolean or `none` literal.

## Changing the presentation

```sh
b view examples/registers/dispatch.bee --function route --register ordinary
b view examples/registers/dispatch.bee --function route --register cases
```

The command prints the selected declaration for copying into an editor. It compiles the original program, substitutes the new declaration in memory and compares the full typed BIR before optimization. This keeps imports, other functions, the function's contracts and branch order in scope. The output may reformat the decision. If an ordinary chain first checks one named value and then another, the first checks become rows. The remaining decision stays inside the fallback. A formula such as `price * count` has no decision rows to render. Asking for a table for that formula produces a diagnostic. The author can choose a form separately for each expression.

## Where a rule holds

Moving both endpoints of a directed displacement by the same amount preserves the difference between them in exact coordinates. Suppose one tick represents half a pixel. In exact mode the endpoints at −2 and −1 ticks are one tick apart. In whole-pixel mode both snap down to −2. Shift both endpoints by one tick: they now snap to −2 and 0. The measured displacement grows from zero to two ticks. Shifting by a whole pixel preserves it under either convention.

[The B example](../examples/registers/displacement.bee) uses a table to select the convention and an arithmetic expression to compute the displacement. The [joint check](../examples/registers/shifts.json) compares a one-tick shift in exact mode and a two-tick shift in whole-pixel mode, across endpoints from −2 to 2.

```sh
b check examples/registers/displacement.bee --strict --joint examples/registers/shifts.json
```

All 25 selected pairs pass. Reversing the subtraction also passes these pairs. A separate reference value catches that error: in exact mode a move from 0 to 2 must return +2. Changing the convention changes which shifts a requirement covers. Changing only the register must preserve the computation. The [regression tests](../tests/test_register_examples.py) cover both distinctions.
