# Decisions as source: functions from examples

Most of a business program is decisions. Who pays what, on which day, above which weight. In most languages the decisions are hidden inside code that somebody wrote to implement them. In B a decision can be the source:

```bee
domain day: "mon", "tue", "wed", "thu", "fri", "sat", "sun"

fn price(child: Bool, day: Text) -> Int pure by examples
example price(false, "mon") == 100
example price(true, "sat") == 0
```

The compiler derives the function from its examples. Other code calls it like any function. When the examples can be read in more than one plausible way, `b check` reports `W_EXAMPLES_OPEN` (rejected by `--strict`) and `b ask` asks for the one example that separates the readings:

```text
fn price by examples (2 examples)
  derived: if child then 0 else 100
  question: price(false, "sat"): 100 or 0?
    100: example price(false, "sat") == 100
        then: if child then 0 else 100 (still open)
    0: example price(false, "sat") == 0
        then: if day == "mon" then 100 else 0 (still open)
```

Each option shows what the function becomes. `b ask FILE --answer 100 --apply` appends the example. The next two questions, `price(true, "mon")` and `price(true, "tue")`, come from competing readings. The last two are neighbor questions. The rule `child and day == "sat"` rests on a single example, so B asks whether Friday and Sunday, the values next to Saturday in the domain, belong to it:

```text
  question: price(true, "fri"): 100 or 0?
  why: only one example supports this case; asking whether the next value in its domain belongs to it
```

After five answers the function is settled as `if child and day == "sat" then 0 else 100`.

## A change is one line

Children now ride free on Sundays as well. B has already asked about Sunday, so the program records that a child paid 100 then. The change has to say so:

```bee
example price(true, "sun") == 0 was 100
```

B asks one question, `price(false, "sun"): 0 or 100?`. Does the change cover adults too? After that answer the function is `if not child then 100 else if day == "sat" then 0 else if day == "sun" then 0 else 100`. Nobody located or edited a rule.

A changed result must name the old one, as above. Without `was`, a contradicting example is an error. With a wrong `was`, the author's picture of the program is stale, and that is also an error. Every current example is a compile-time fact about the final program, including examples of ordinary functions:

```bee
fn total(child: Bool, day: Text) -> Int pure = price(child, day) + 10
example total(true, "sat") == 10
```

## Mixing decisions and code

[`examples/learn/shop.bee`](../examples/learn/shop.bee) defines shipping and a member discount with twelve examples and writes the order total as one line of ordinary B. An example on `total` checks the formula and both derived functions together. `b check --strict` accepts it, and `b ask` reports both functions as settled:

```text
fn shipping by examples (8 examples)
  derived: if express then 90 else if weight < 10 then 30 else 60
```

## What B searches

The candidate functions are ordered rule lists:

```text
if A then x else if B and C then y else z
```

- At most four cases, each a conjunction of at most two tests.
- A test is a Bool parameter or its negation, `p == v` for a Text or Int value, or `p < t` / `p >= t` for an Int parameter. Values come from the examples, from comparisons with a parameter of the same name elsewhere in the program, and from a `domain`. Thresholds lie at example values and at the middle of every gap between known values.
- Results are literals taken from the examples.

The **simplest** rules have the fewest cases plus tests. Among them, the canonical rule's fallback is the result most examples share. B also considers **plausible** rules with one more case or test than the simplest. A question is needed when two of these readings give different results for some input B compares:

| Parameter | Inputs compared |
| --- | --- |
| Bool | both values |
| Text with a `domain` | every domain value, in declared order |
| Text without a domain | values B knows, plus one value no example names (`<another value>`) |
| Int with a `domain` | every domain value |
| Int without a domain | known values, midpoints of gaps and one step outside the outermost values |

Plausible readings can raise questions only within the range the examples span. Without that limit, questions could step outward forever. A question that only concerns `<another value>` comes from the simplest readings alone and cannot be answered automatically: the owner adds an example with a real value.

When no readings compete, B looks for a **single-witness case**: a case only one example supports, with a test `p == v` on a domain value. It then asks about the values next to `v` in the declared order, keeping the witness's other arguments, unless that input is already stated or already gives the case's result. The declared order is the only notion of similarity B has here. For days of the week it fits well. For an arbitrary list it may not.

B picks the input that splits the readings most evenly. It prefers inputs close to the newest example in categorical values and far from all examples on integer axes. A change therefore raises questions about its neighbors, and an integer boundary is found by halving the gap. In the age example a domain of 0–99 and two starting examples lead to twelve questions that locate both 12 and 65.

## `domain`

```bee
domain day: "mon", "tue", "wed", "thu", "fri", "sat", "sun"
domain age: 0, 1, 2, 3
```

A domain names every value of an input called `day`. As elsewhere in B, a shared parameter name denotes the same input. B rejects example, `also` and `like` arguments and literal comparisons with that name that fall outside the domain, so `"sön"` is a compile error. The domain does **not** yet add a runtime check on calls.

## Limits

- **Simplicity is a guess.** Questions come from readings at most one test more complex than the simplest, and from domain neighbors of single-witness cases. A policy several cases away from the simplest reading is missed, as the access-control case in the [experiment](../experiments/decisions/README.md) shows. Without neighbor questions, the weekend policy settles on Sunday alone.
- **The rule language is small.** Results are literals: `10 * items` is refused with `E_EXAMPLE` and should be written as code. Parameters are Bool, Int or Text. A search limit protects compile time and also produces a refusal.
- **The owner answers.** B decides which questions to ask, but it cannot judge whether an answer is right.
- **A changed boundary needs restated examples.** Moving the child limit from 12 to 14 contradicts existing answers at 12 and 13. Each must be restated with `was`, and the compiler lists them one at a time.
- `next`, registers and the revision checker do not yet handle functions defined by examples.
