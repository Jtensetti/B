# B for models: everything needed to write a program

Read this page instead of the full reference. B looks like a mix of Python and TypeScript. It is statically typed, and its expressions are pure unless they call another language. It runs with `b run file.bee`, and `b check --strict file.bee` reports problems without running.

## A complete program

[`examples/for-models/quote.bee`](../examples/for-models/quote.bee) quotes parcels with a Python carrier library that works in pounds and dollars. It matches misspelled product names with an npm package and prices in kronor. It passes `b check --strict`.

```bee
use py:carrier as carrier
use py:json as json
use js:"fastest-levenshtein" as words

record Item { weight_kg: Float, volume_l: Option[Float] }
record Order { id: Text, product: Text, qty: Int, express: Option[Bool] }
record Input { orders: List[Order], catalog: Dict[Text, Item], usd_to_sek: Float }

foreign json.loads(Text) -> Input
foreign carrier.rate(Mass[lb], Bool) -> Money[USD]

let data = json.loads(read_line())
let names = sorted(keys(data.catalog))

fn find(name: Text) -> Option[Text] =
    let near = if len(names) == 0 then "" else words.closest(name, names)
    if name in data.catalog then name
    else if len(names) > 0 and words.distance(name, near) <= 2 then near
    else none

fn billable(o: Order, item: Item) -> Mass =
    let actual = o.qty * (item.weight_kg * 1 kg)
    let volume = o.qty * ((item.volume_l ?? 0.0) * 1 l)
    let dimensional = (volume as inch3) / 139 * 1 lb
    max(actual as kg, dimensional as kg) * 1 kg

fn price(o: Order, name: Text) -> Float =
    let item = data.catalog[name]
    if item != none
    then round((carrier.rate(billable(o, item), o.express ?? false) as USD) * data.usd_to_sek, 2)
    else 0.0

let found = {o.id: find(o.product) ?? "" for o in data.orders where find(o.product) != none}
let quotes = {o.id: price(o, found[o.id] ?? "") for o in data.orders where o.id in found}
print to_json({
    quotes_sek = quotes,
    total_sek = round(sum(values(quotes)), 2),
    unknown = sorted([o.id for o in data.orders where not (o.id in found)]),
    matched = {o.id: found[o.id] ?? "" for o in data.orders where o.id in found and not (o.product in data.catalog)}})
```

## Syntax

| Need | Write |
| --- | --- |
| Values | `1`, `2.5`, `"text"`, `true`, `none`, `[1, 2]`, `{"key": 1}` |
| Types | `Int`, `Float`, `Text`, `Bool`, `List[T]`, `Dict[Text, T]`, `Option[T]`, a record name |
| A binding | `let x = ...` (top level, or at the start of a function body) |
| A function | `fn f(a: Int, b: Text) -> Text = expression` |
| Local steps | lines `let y = ...` after `=`, then the result expression on the last line |
| A condition | `if c then a else b`. Lines may start with `then` or `else`. Every `if` needs an `else` |
| A missing value | `x ?? fallback`. After `if x != none then ...`, `x` is no longer optional |
| A list from a list | `[f(x) for x in xs where cond]` |
| A dictionary from anything | `{key: value for k, v in d where cond}` (keys are Text) |
| An item, a key | `xs[0]` and `d["key"]` both give an `Option`; use `??` |
| Membership | `x in xs`, `key in d`, `"sub" in text` |
| Records | `record R { a: Int, b: Option[Text] }`, build `{a = 1}`, read `r.a` |
| Output | `print value`, `print to_json(value)` |
| Input | `read_line()` reads one line of standard input |
| Core words | `len sorted keys values text join round sum min max abs to_json read_line` |
| Long expressions | wrap in `( ... )` or `[ ... ]` to continue on the next line |

There are no loops, no assignment, no statements inside functions and **no comments**: `#` is a syntax error. Transform collections with `for ... in ... where` and summarize with `sum`, `min`, `max` and `len`.

## Other languages

```bee
use py:module as m
use js:"package" as p
foreign m.function(Int, Text) -> Float
```

`use py:` imports from Python's standard library, installed packages and files next to the program. `use js:` imports npm packages from `node_modules`. `foreign` declares a signature that B could not read.

B reads Python type hints and `.pyi` stubs on its own. The npm packages `semver` and `fastest-levenshtein` are already typed. Declare a function with `foreign` when B says it has no signature. Calls to other languages are not `pure`, so leave `pure` off functions that make them.

## Checks worth using

- **Units at a border.** Write `foreign lib.f(Mass[lb]) -> Length[ft]` when a library uses particular units. Then pass `2 kg` or `x * 1 kg`, and B converts. Read a result with `as m`. Adding kilograms to meters, or kronor to dollars, is a compile error. Units: `kg g lb oz m km cm mm inch ft mi l dl ml inch3 s min h day USD SEK EUR kr` and [more](units.md).
- **Examples.** `example f(2) == 4` is checked on every compile. `example lib.f(1 h) == 9.5 gal within 0.01 gal` checks a library function where the program reaches it.
- **Strictness.** `b check --strict` rejects warnings such as untyped foreign calls.

## Common errors

| Message | Fix |
| --- | --- |
| `Unexpected token ... ELSE` | Every `if` needs `else`. Inside a function, a line may start with `else` |
| `expected Int, got Option[Int]` | Add `?? fallback`, or test `if x != none then ...` first |
| `Unspecified Python symbol` | Add a `foreign` declaration with types |
| `declared pure, but has effects: foreign` | Remove `pure`: the function calls another language |
| `print needs a plain number, got Length` | Write `print x as m` |
