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
| A missing value | `x ?? fallback`, also `x ?? {}` and `x ?? []`. After `if x != none then ...`, `x` is no longer optional. Division by a value is accepted inside `if r > 0.0 then ... / r` |
| A list from a list | `[f(x) for x in xs where cond]` |
| A dictionary from anything | `{key: value for k, v in d where cond}` (keys are Text) |
| An item, a key | `xs[0]` and `d["key"]` both give an `Option`; use `??` |
| Membership | `x in xs`, `key in d`, `"sub" in text` |
| Records | `record R { a: Int, b: Option[Text] }`, build `{a = 1}` or `R { a = 1 }`, read `r.a` |
| Output | `print value`, `print to_json(value)` |
| Input | `read_line()` reads one line of standard input |
| Core words | `len sorted keys values text join round ceil floor sum min max abs upper lower trim range to_json read_line` (`range(3)` is `[0, 1, 2]`) |
| Long expressions | wrap in `( ... )` or `[ ... ]` to continue on the next line |

There are no loops, no assignment, no statements inside functions and **no comments**: `#` is a syntax error. Transform collections with `for ... in ... where` and summarize with `sum`, `min`, `max` and `len`.

## Other languages

```bee
use py:module as m
use js:"package" as p
foreign m.function(Int, Text) -> Float
```

A function that raises an exception for some inputs is declared with an `Option` result: `foreign tariff.zone(Text) -> Option[Int] on KeyError` gives `none` instead of stopping. B has no `try`.

Go, Rust and C# libraries next to the program are borrowed the same way. B reads their signatures with each language's own tools:

```bee
use go:"./libs/tariff" as tariff
use rust:"./libs/geo" as geo
use cs:"./libs/Tax" as tax
foreign tariff.Zone(Text) -> Option[Int] on error
let km = geo.road_km(59.3, 18.1, 57.7, 11.9)
let rate = tax.Vat.Rate("SE")
```

A Go module is a directory with `go.mod`, a Rust crate a directory with `Cargo.toml` and `src/lib.rs`, and a C# project a directory with one `.csproj`, whose public static methods are called as `tax.Class.Method(...)`. A Go `error`, a Rust `Err` or a C# exception stops the program, unless the function is declared `-> Option[T] on error`, which gives `none` instead. A Python module in a subfolder is `use py:libs.calendar.workdays as cal`.

`use py:` imports from Python's standard library, installed packages and files next to the program. `use js:` imports npm packages from `node_modules`. `foreign` declares a signature that B could not read.

Objects of another language get a name and typed methods:

```bee
use py:datetime as dt
foreign type Date = dt.date
foreign dt.date.fromisoformat(Text) -> Date
foreign Date.isocalendar() -> List[Int]
foreign Date.toordinal() -> Int
```

Then `dt.date.fromisoformat(day).isocalendar()` is a typed call, and a Python tuple arrives as a `List`.

B reads Python type hints and `.pyi` stubs on its own. The npm packages `semver` and `fastest-levenshtein` are already typed. Declare a function with `foreign` when B says it has no signature. Calls to other languages are not `pure`, so leave `pure` off functions that make them.

## Changing a rule

When a request widens a rule that already exists ("children ride free on Sundays too"), do not edit the condition by hand. Declare the extension and ask B what it means:

```bee
fn free_entry(child: Bool, day: Text) -> Bool pure = child and day == "sat"
fn ticket(child: Bool, day: Text) -> Int pure = if free_entry(child, day) then 0 else 100
fn fee(child: Bool, day: Text) -> Int pure = if child and day == "sat" then 0 else 10
fn total(child: Bool, day: Text) -> Int pure = ticket(child, day) + fee(child, day)

also free_entry(true, "sun")
```

Running `b ask change.bee` compares the new case with the nearest case the rule already covered, Saturday. It then reports every result that still differs:

```text
  question: total(true, "sun"): 10 or 0?
    10 (as declared): also free_entry(true, "sun") keeping fee
    0 (like free_entry(true, "sat")): also free_entry(true, "sun") like (true, "sat")
        and in fee: child and day == "sat" -> free_entry(child, day)
```

That is exactly the question to put to the owner. Then write the answer back with `b ask change.bee --answer 0 --apply`. When the existing case already settles the meaning, `b ask` says so and asks nothing. Rules used with `also` must be `pure` functions returning `Bool`, and the functions `b ask` compares must be `pure` with plain parameters.

## Checks worth using

- **Units at a border.** Write `foreign lib.f(Mass[lb]) -> Length[ft]` when a library uses particular units. Then pass `2 kg` or `x * 1 kg`, and B converts. Read a result with `as m`. Adding kilograms to meters, or kronor to dollars, is a compile error. A record field may hold a quantity (`net: Money[SEK]`), and `sum([l.net for l in lines])` keeps the currency. Units: `kg g lb oz m km cm mm inch ft mi l dl ml inch3 s min h day USD SEK EUR kr` and [more](units.md).
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
| A Python `KeyError` or `ValueError` stops the run | Declare the call `-> Option[T] on KeyError` and handle `none` |
