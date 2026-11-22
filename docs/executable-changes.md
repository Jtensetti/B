# Executable changes

An `also` declaration extends a named, explicitly pure B function returning `Bool`. For these exact inputs it returns true. For every other tuple the original body supplies the result. A caller such as the ticket calculator uses the extended function automatically.

```bee
fn free_entry(child: Bool, day: Text) -> Bool pure = child and day == "sat"
fn price(child: Bool, day: Text) -> Int pure = if free_entry(child, day) then 0 else 100
fn seats(child: Bool, day: Text, available: Int) -> Int pure = available - 1
fn recipient(gift: Bool) -> Text pure = if gift then "buyer" else "guest"

also free_entry(true, "sun") keeping seats, recipient
```

The declaration applies throughout the module, including calls textually before it. Arguments must be ground literals of the exact parameter types. B supports Bool, Int, Text and finite Float in this form. It checks the original target signature and any precondition and postcondition at the selected tuple with result `true`. Duplicate tuples are rejected. An earlier pending `next` edit can change the fallback body when applied. Persistent `also` facts retain priority.

## What a protected result means

For the same inputs, moving a ticket into the free category must preserve the named results. B establishes this by checking the transitive dependencies of each named function in unoptimized, typed BIR. The check runs during ordinary compilation, including `run`. In the booking example, changing the body of `seats` to subtract two when `price(child, day) == 0` makes the declaration fail before the program runs. The diagnostic identifies the path from `seats` through `price` to `free_entry`.

Protect the observable that receives the original request. A helper `reserve(quantity)` can still return the same value for the same quantity while its caller changes the quantity it supplies. The end-to-end function `seats(child, day, available)` covers that case. Protection is local to the rule on its line. In a batch extending two different rules, list the observable on both lines to protect it from both. Omit `keeping` to allow downstream dependencies of a rule to follow it.

The dependency check supports pure scalar functions, including references to immutable scalar bindings. A dependency in a dead branch also prevents certification. Executing a database write or sending a receipt through an external service falls outside this guarantee. The example protects the computed seat count and recipient.

## Execute a declaration or check a separate implementation

A change can live alongside the program or in a separate B source file. `--with` on `check`, `build` or `run` attaches a file containing only `also` declarations. It leaves the input files untouched.

```sh
b run examples/also/booking.bee --with examples/also/sunday.bee
cat examples/also/booking.bee examples/also/sunday.bee > revised.bee
b revision examples/also/booking.bee revised.bee --delta examples/also/sunday.bee
```

The second command constructs a candidate for illustration. The third also works on an independently written revision. It derives the expected program from the frozen base plus the specified delta. Every exported function, its signature and its contract are part of the comparison. Including the same file with `--delta` pins the authorization independently of the candidate. Omitting the option trusts the newly added declarations in the candidate. A hand-written candidate can implement a new pinned rule directly, while already accepted declarations must be retained.

The revision checker accepts closed modules of explicitly pure scalar functions and ordered top-level scalar prints. It compares the rendered output of the runnable program, including line breaks. The number of print sites is part of the interface. It can establish equivalence using identical checked operations or an exhaustive comparison for supported Boolean and equality-based rules. For unbounded equality-only inputs, representatives include all observed literals and enough distinct fresh values to cover equality between arguments. On other operations it can often find a concrete disagreement. A successful comparison requires an actual extension at every specified tuple. A change already true in the base, a changed public interface or a broken protection is rejected. Imports, top-level bindings, effects beyond the supported console prints and unsupported observations yield an inconclusive result. A revision targeting a Float rule or a rule with contracts may compile successfully and still have an inconclusive prior value. A possible failure in an earlier print can also prevent a witness for a later one.

Only `proved` yields exit status zero from `b revision`. With `--json`, `counterexample` supplies the offending function, arguments and results, or an output position and the differing output prefixes. `unknown` means the implementation could not establish equivalence. `invalid` includes malformed changes and violated constraints.
