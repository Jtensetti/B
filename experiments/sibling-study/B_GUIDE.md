# B Language Reference (v0.20)

Statically typed, expression-oriented language with records, units, currencies, decision tables, typed summaries, ordered history counts, and direct Python/.NET/npm/Go/Rust interop.

Syntax: No `#` comments. Newlines end top-level statements; multiline expressions work inside `(...)`, `[...]`, `{...}`, and after `=`, `then`, `else`, `in`, `=>`, `|>`, `,`. Separate `record`/`cases`/`summarize`/`with` entries by newline, `;`, or `,`.

## Types, Units, Currencies, Records
- Types: `Int`, `Float`, `Bool`, `Text`, `Option[T]`, `List[T]`, `Dict[Text, T]` (`none` is `Option[T]`; unwrap with `opt ?? fallback`).
- Units & currencies (statically checked):
  ```bee
  unit m, s
  unit km = 1000 m
  currency EUR, SEK
  let d: Float[km] = 2.5 as km
  let meters: Float[m] = d to m
  let raw: Float = scalar(meters)
  ```
- Nominal records (used by `from_json`; positional or named/shorthand construction):
  ```bee
  record Item { id: Text; size: Int; fee: Float[EUR] }
  let x = Item(id: "a", size: 10, fee: 5.0 as EUR)
  let y = x with { fee: x.fee * 1.1 }
  ```
- Structural record literals (typed `.field` access, `with`, `json_encode`; shorthand `ok` means `ok: ok`):
  ```bee
  let out = record { total: 5, ok, label: "done" }
  ```

## Functions, Comprehensions, Pipelines, Rule Extensions
```bee
fn add_tax(p: Float[EUR]) -> Float[EUR] pure = p * 1.25
fn pair(x: Int) pure = record { x, doubled: x * 2 }
let ys = [x * 2 for x in [1, 2, 3] where x > 1]
let norm = " Hi " |> str_trim |> str_lower
```
- `-> T` is optional on non-recursive functions (inferred statically, ideal when returning `record { ... }`).
- `also pred(a, b) keeping fn1, fn2` extends a `pure` `Bool` predicate while statically verifying `fn1, fn2` (including dimensioned scalar functions) do not depend on `pred`.

## Decision Tables (`cases var`), Typed Summaries, Ordered History
```bee
fn tier(n: Int) -> Text pure = cases n {
    < 100 => "tiny"
    <= 1000 => "standard"
    else => "large"
}
let s = summarize x in xs {
    total: count
    hits: count where x.ok
    total_km: sum x.dist where x.ok
    hi: max x.val where x.ok default 0
}
let n = s.total
let m = s.total_km to m
```
- `summarize` allows mixed types (`Int`, `Float`, `Float[dim]`) in one pass with direct `.field` access (no `?? 0`).
- Ordered counts (pure `Int`/`Bool`/`Text`/record-field predicates; no floats or calls):
  - `count adjacent past, now in xs where past.bad and now.bad`
  - `count earlier past, now in xs where past.ms + 300 < now.ms`

## Built-ins
- Numeric: `len(x)`, `abs(x)`, `min(a, b)`, `max(a, b)`, `round_even(f) -> Int`, `round_away(f) -> Int`, `div_euclid(a, b)`, `rem_euclid(a, b)`, `rem_trunc(a, b)`, `scalar(x)`, `to_text(x)`, `to_float(i)`, `to_int(f)`
- Strings: `str_contains(s, sub)`, `str_starts(s, p)`, `str_ends(s, p)`, `str_lower(s)`, `str_upper(s)`, `str_trim(s)`, `str_split(s, sep)`, `str_join(xs, sep)`, `str_replace(s, old, new)`
- JSON I/O: `stdin_text() -> Text`, `let req: MyRecord = from_json(stdin_text())`, `json_encode(val) -> Text`, `print expr`

## Direct Foreign Library Imports
Functions calling foreign libraries must omit `pure`. Built-in manifests (`net:`, `go:`, `rs:`, `js:semver`, `js:"node:path/posix"`, `py:statistics.mean`, `py:math.sqrt/pow`) are already typed—do NOT write `foreign` for them; only declare `foreign` for other Python or uncurated npm functions.
- Python: `use py:urllib.parse as urls` + `foreign urls.unquote(Text) -> Text`; `use py:statistics as stats` (`stats.mean(List[Float]) -> Float`)
- .NET: `use net:System.Math as NetMath` (`Sqrt`, `Pow`, `Abs`, `Min`, `Max`, `Round`, `Floor`, `Ceiling`); `use net:System.Text.RegularExpressions.Regex as Rx` (`IsMatch(Text, Text) -> Bool`, `Replace(Text, Text, Text) -> Text`); `use net:System.Uri as NetUri` (`UnescapeDataString`)
- Node/npm: `use js:"node:path/posix" as path` (`normalize`, `basename`, `dirname`, `extname`, `join`); `use js:semver as sv` (`valid(Text) -> Option[Text]`, `satisfies(Text, Text) -> Bool`, `compare(Text, Text) -> Int`, `maxSatisfying(List[Text], Text) -> Option[Text]`)
- Go: `use go:strings as gstr` (`TrimSpace`, `ToLower`, `ToUpper`, `Contains`, `HasPrefix`, `HasSuffix`, `ReplaceAll`); `use go:math as gmath` (`Round`, `RoundToEven`, `Floor`, `Ceil`, `Abs`, `Sqrt`, `Hypot`)
- Rust: `use rs:std.str as rstr` (`len_chars(Text) -> Int`, `len_bytes(Text) -> Int`, `trim`, `to_lowercase`, `to_uppercase`, `contains`); `use rs:std.i64 as ri` (`rem_euclid(Int, Int) -> Int`, `div_euclid`, `clamp`); `use rs:std.f64 as rf` (`round`, `round_ties_even`, `hypot`, `sqrt`)
