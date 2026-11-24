# B language reference — implemented experimental v0.31

This document specifies **the implemented subset**, not the eventual B 1.0 ambition. The authoritative executable grammar is [`b_lang/syntax.lark`](../b_lang/syntax.lark), and the static type system is implemented in [`b_lang/types.py`](../b_lang/types.py) and [`b_lang/compiler.py`](../b_lang/compiler.py). Where this document and the compiler differ, that is a bug to fix and test.

For source adoption and contract analysis across functions, see [source adoption](source-adoption.md), [contract analysis](composition.md) and [conditional guarantees](conditional-guarantees.md).

## Executable rule extensions

`also free_entry(true, "sun") keeping seats, recipient` adds a ground input tuple to a pure native Boolean predicate. The optional `keeping` clause protects named functions against a transitive dependency on that predicate. Source order does not change the meaning of a fact. See the [grammar, examples and revision checker](executable-changes.md).

`also free_entry(true, "sun") like (true, "sat")` additionally requires the new case to be indistinguishable from a case the rule already covered, for every pure function that shares an input name with the rule. `b ask` finds that case when the declaration omits it and turns a remaining difference into one question. See [precedent questions](precedent-questions.md).

`fn price(child: Bool, day: Text) -> Int pure by examples` declares a pure function without a body. The compiler derives an ordered rule list from the `example price(true, "sat") == 0` statements for that name. `example` statements also check ordinary functions. A changed result must be written `... == 120 was 100`. `domain day: "mon", ..., "sun"` lists the values of any parameter named `day`. See [decisions as source](examples.md).

`know kalender` includes domains and groups that ship with B. `group helg of dag: "lördag", "söndag"` names a subset, and `dag in helg` tests membership. Names may contain any letters in normalized Unicode form. See [what B knows](knowledge.md).

A quantity literal is a number and a unit (`5 km`, `90 km per h`, `19.5 kr`). `x as km` converts to a plain number. Types such as `Length`, `Money[SEK]` and `Rate[SEK, USD]` declare dimensions. The checker rejects mixed dimensions and currencies, then erases units to Float SI values. See [units](units.md).

`example alias.member(args) == value [within tolerance]` states a fact about an imported function. It is type checked while compiling and executed where it stands. `b check --library-examples` runs each such fact separately. See [decisions about libraries](library-examples.md).

## 1. Source form and tokens

B source is UTF-8. **`.bee` is the recommended extension**; `.b4` is an optional playful alias, with `.bsrc` and `.b` retained for compatibility. `.bi` is *not* adopted: FreeBASIC already uses it for headers. `.b4` also has a historical non-B use and is not reserved. The CLI validates the file contents regardless of suffix.

A newline separates complete top-level statements. After the assignment `=` in a function or a let declaration, its expression can begin on the following line. Inside a `cases` table or `summarize` expression, rows can occupy separate lines or share a line using semicolons. Blank lines are ignored. A bare `#` introduces a syntax error. A hash inside a string is data. To convert a B 0.13 file, run `b migrate-comments OLD.bee > converted.bee` with a separate output path. Identifiers match `[A-Za-z_][A-Za-z0-9_]*`; `_b_` is reserved for compiler internals. Strings are JSON-compatible double-quoted literals. Integers have decimal notation; floating literals have a decimal point; negative values use unary `-`. No exponent literals or arbitrary Unicode identifiers yet. Whitespace between tokens is ignored.

## 2. Grammar

The following EBNF captures the implemented constructs; the Lark grammar governs exact precedence and parsing:

```ebnf
program       = { newline | statement, newline }, [statement] ;
statement     = permit | use | adopt | foreign | let | fn | print | assert | next_edit ;
permit        = "permit", "[", [identifier, {",", identifier}], "]" ;
use           = "use", (("py" | "net"), ":", path | "js", ":", (path | string)), "as", identifier ;
adopt         = "adopt", "py", ":", path, "as", identifier ;
foreign       = "foreign", path, "(", [type_list], ")", "->", type ;
let           = "let", identifier, [":", type], "=", {newline}, expression ;
fn            = "fn", identifier, "(", [parameters], ")", "->", type,
                ["pure"], ["requires", expression], ["ensures", expression], "=", {newline}, expression ;
next_edit     = "next", identifier, "when", expression, "=>", expression ;
print         = "print", expression ;
assert        = "assert", expression ;
parameters    = parameter, {",", parameter} ;
parameter     = identifier, ":", type ;
type_list     = type, {",", type} ;
type          = identifier, ["[", type, {",", type}, "]"] ;
expression    = "if", expression, "then", expression, "else", expression
              | history_count | coalesce_expression ;
history_count = "count", ("adjacent" | "earlier"), identifier, ",", identifier,
                "in", expression, "where", expression ;
coalesce_expression = logical_expression, ["??", coalesce_expression] ;
list          = "[", [expression, {",", expression}], "]" ;
dictionary    = "{", [pair, {",", pair}], "}" ;
pair          = expression, ":", expression ;
case_table    = "cases", identifier, "{", {newline}, row, {row},
                "else", "=>", expression, [";"], {newline}, "}" ;
row           = comparison_operator, scalar_threshold, "=>", expression, separator ;
summary       = "summarize", identifier, "in", expression, "{", {newline},
                field, {separator, field}, [";"], {newline}, "}" ;
field         = identifier, ":", ("count", ["where", expression]
              | "sum", expression, ["where", expression]
              | ("min" | "max"), expression, "default", signed_integer) ;
signed_integer = ["+" | "-"], decimal_integer ;
lookup_tail   = "[", expression, "]" ;
separator     = ";", {newline} | newline, {newline} ;
```

The `b next --from-short` command accepts a [separate compact edit format](handoffs.md#compact-input).

A top-level `next` declares a pending edit on a source function. The condition and replacement use the target function’s scope. [Listing, applying and checking an edit](handoffs.md).

A case table is an expression. It compares the named value against each scalar literal in order, using the ordinary comparison operators and type rules. The first matching row supplies the result, with a mandatory final fallback. Numeric thresholds can be negative. See [decision tables and source views](registers.md).

Expressions also allow literals (`true`, `false`, `none`, numbers, strings), references, calls, attribute access and grouping. Precedence (highest to lowest): postfix attribute/call/key lookup, unary `not`/`-`, multiplication/division/modulo, addition/subtraction, comparison, `and`, `or`, `??` (right associative), conditional. Both conditional branches are statically type-checked, even if the condition is constant.

### Transforming collections, records and core words

`[expr for x in xs where cond]` builds a list. `{key: value for k, v in d where cond}` builds a `Dict[Text, V]`. A list gives one name per item. A dictionary gives its key, or its key and value. `where` is optional. The names are local to the expression and may not shadow names in scope.

`record Booking { child: Bool, day: Text, note: Option[Text] }` declares a structural record type, as in TypeScript. `{child = true, day = "sat"}` builds a record, and `b.day` reads a field. An `Option` field may be left out and then reads as `none`. At runtime a record is a dictionary, so JSON from Python or JavaScript enters through the usual border check. A missing required field stops the program there, and undeclared fields are not carried along. Records may refer to records declared later, but not to themselves.

`xs[0]` reads a list item as an `Option`. A position outside the list gives `none`, and `xs[-1]` is the last item. `x in xs` tests whether a list contains an item, a dictionary a key, or a text a substring. If the name after `in` is a declared group, it tests group membership instead.

A newline inside `(...)` or `[...]` continues the expression, as in Python. Inside `{...}`, newlines are allowed after commas and around the parts of a dictionary transform.

A function body may start with local bindings, one per line, before its result:

```bee
fn describe(prices: Dict[Text, Int], item: Text) -> Text =
    let price = prices[item]
    let label: Text = "item " + item
    if price != none then label + " costs " + text(price) else label + " is unknown"
```

Each binding is evaluated once. A binding may not hide a function.

After a test `x != none`, `x` has its inner type wherever the test is known to hold. That includes the `then` branch, the `else` branch of `x == none`, both sides of `and`, under `not`, and the item expression of `[... for ... where x != none]`. Only plain names narrow.

`len`, `sorted`, `keys`, `values`, `text`, `join`, `round`, `sum`, `min`, `max`, `abs`, `read_line` and `to_json` are typed core words. `min` and `max` of a list give an `Option`, and of two values give the larger or smaller value. A line may start with `then` or `else` to continue an `if`. Python's builtins run them, but B types them for any element type. `text(true)` is `"true"`. A program's own function of the same name takes precedence.

### Collection expressions

`summarize item in source { fields }` evaluates a list source once. It visits items in order and updates each named field in declaration order. The item name is local to the fields. Each optional `where` takes a Boolean and runs before the associated value expression. Counts and integer sums start at zero. `min` and `max` take an integer expression and require an explicit signed integer default for an empty source. With any items present, their extrema come entirely from those items. Each field name occurs once. Repeated expressions in separate fields can each execute a call. Existing purity and effect rules apply to the entire expression. The iteration uses the original list membership even when a field calls an opaque function that changes the list. A shallow snapshot protects that case. A count with no filter uses the list length directly.

The result is a `Dict[Text,Int]` in field order. A dictionary accepts a postfix text key, for example `report["early"]`. The result of a lookup is optional. A missing key and a key whose value is `none` both give `none`. Use `??` for a fallback. Dictionary lookup accepts computed keys, so a typo at a lookup site can select its fallback.

### Ordered counts

`count adjacent p, q in source where predicate` evaluates the list source once. For each position after the first, `q` is its item and `p` is its immediate predecessor. A true predicate adds one to the result. Changing `adjacent` to `earlier` counts each current position with at least one matching earlier item, even when many earlier items qualify. Empty lists and singletons return zero. Consecutive matches can share an item. The result has type `Int`. For a source of length n it lies between zero and max(0, n−1).

Both names are local to the predicate and must be distinct from each other and names already in scope. The predicate must have type `Bool`. It admits integer arithmetic with `+`, `-` and `*`, Boolean expressions, conditionals, scalar comparisons, typed dictionary lookup, optional values and `??`. Opaque calls, dynamic guards, division and floating-point calculations fall outside this fragment. These restrictions allow the compiler to cache an earlier projection or evaluate it when an item arrives. The source can itself be a normal B expression with effects. Wrap the count in parentheses when comparing or doing arithmetic with its result.

| Pattern | State during counting | Work in predicate evaluations |
| --- | --- | --- |
| Adjacent, conjunction of separate previous and current tests | Previous test result | Linear |
| Other adjacent predicate | Previous item and a presence flag | Linear |
| Earlier, ordered integer comparison of separate projections | Least or greatest earlier projection | Linear |
| Other earlier predicate | Searches the already supplied list | Up to n(n−1)/2 pair tests |

`b ir FILE --optimized` displays the selected plan. A negated integer order such as `not (p >= q)` has the same plan as `p < q`. The public function still receives a list and checks its declared parameter type. Interpreting an interval rule as an overlap check also depends on the input convention. The [runnable example](../experiments/ordered-history/README.md) handles both ordered and unordered starts.

## 3. B types

| B type | Current Python-backed runtime value | Notes |
| --- | --- | --- |
| `Int` | Python `int` | Excludes booleans; no explicit integer overflow limit in v0.4 |
| `Float` | Finite Python `float` | A compatible `Int` is converted to float at typed boundaries; may round |
| `Bool` | Python `bool` | Not assignable to `Int` |
| `Text` | Python Unicode `str` | No mutable text operations in the B subset |
| `None` | Python `None` | Literal or function return; *not* allowed as a standalone `let` annotation |
| `Option[T]` | `T` **or** `None` | Explicitly nullable; cannot silently narrow to `T` |
| `List[T]` | Python list | Members guarded recursively at typed boundaries |
| `Dict[Text, T]` | Python dict with string keys | Keys must be `Text`, values guard recursively; snapshots across typed boundaries |
| `Any` | Dynamic Python value | Explicit loss of static type information; narrowing needs runtime guards |

Subtyping/assignability is limited to identity, `Int -> Float`, `T -> Option[T]`, `None -> Option[T]`, recursive container compatibility and `Any` with guarded narrowing. A `Dict` key type must be `Text`. `if ... then Int else None` infers `Option[Int]`. `optional ?? default` safely extracts a value or uses the fallback; it requires `Option[T]` on the left and a compatible value on the right. The left operand is evaluated exactly once and the fallback is lazy. Incompatible *fully known* element types in a list or dictionary are rejected before running; unknown dynamic values produce boundary warnings/guards where they are narrowed. Empty lists and dicts infer an `Any` value type until context narrows them.

In 0.8, a common `Float` type converts the selected integer value at the join. For example, `if true then 9007199254740993 else 0.0` evaluates to `9007199254740992.0`. The same conversion applies to `??`, mixed numeric elements of list and dictionary literals, and list concatenation. The checker uses the rounded value when evaluating constant comparisons.

Ordering operators accept compatible numbers, text, booleans and lists of orderable elements. Lists compare lexicographically. For dictionaries and nullable values, use equality or inequality. Use `??` to supply a default before ordering a nullable value. An operand typed `Any` can still fail its comparison at runtime.

Example:

```text
let entries: Dict[Text, Option[Int]] = {"known": 9, "missing": none}
let maybe: Option[Int] = if true then 4 else none
let sure: Int = maybe ?? 0
print entries
```

## 4. Evaluating B code

`let` binds immutable names once. `fn` declares an expression-bodied typed function with positional parameters and checked return type. Top-level statements are evaluated in order. Calls, arithmetic, boolean operators, and floating-point behavior are currently lowered to Python AST and inherit its execution model. Short-circuiting applies to `and`, `or` and conditionals. This is not a native B binary compiler.

Known constant division by zero causes `E_DIV_ZERO`. A statically false assertion causes `E_ASSERT`; an unproven assertion gets `W_RUNTIME_ASSERT` and is rejected in strict mode. The runtime assertion is emitted as an exception-raising check, not a Python `assert` removed by optimization. Arbitrary nontermination, resource exhaustion, unexpected foreign exceptions and incorrect results with otherwise correct types are not proved away.

## 5. Foreign library imports

```text
use py:b_examples.poly_lib as lib
let a: Int = lib.describe(41)
let b: Text = lib.describe("hello")
let result: Option[Int] = lib.find_code("Ada")
let doubled: Dict[Text, Float] = lib.adjust({"x": 2.0})
print doubled
```

B reads a neighboring `.pyi` stub, else a `.py` source file, via a restricted Python AST interpreter, without evaluating its annotation expressions. It supports typed positional functions with optional trailing default arguments, `list[T]`, `dict[str,T]`, `Optional[T]`, `T | None`, `typing.Union[T,None]`, and sets of supported `@overload` alternatives. It does **not** yet support Python type variables, keyword-only/variadic parameters, complex unions, classes and methods, `TypedDict`, protocol typing or broad generic metadata. Unknown forms are skipped; B never invents a static signature. For dotted names B inspects each package's search locations without running filesystem package initializers. Custom Python import hooks remain trusted.

An overload is selected only if its argument types distinguish it unambiguously. The checker accepts a **single** matching overload, or a **uniquely exact** alternative, and rejects otherwise with `E_OVERLOAD_AMBIGUOUS`. It does **not** implement the complete Python typing specification's overload algorithm. An overloaded function whose argument is `Any` and could select different return types is rejected rather than guessed. `b inspect py:... --json` lists each supported overload separately.

A used `.pyi` signature is a trusted *assumption*. Typed foreign arguments and results are checked at runtime, including nested lists, dictionaries and nullable values, but the correctness of the library's *behavior* is not thereby proved. The user may still explicitly declare a Python signature with `foreign` when metadata cannot represent it. Unsupported Python calls are dynamic and warn with `W_UNCHECKED_FOREIGN`.

A Python function that raises an exception for some inputs is declared with an `Option` result and the exceptions it may raise: `foreign tariff.zone(Text) -> Option[Int] on KeyError, ValueError`. The call then gives `none` when the function raises one of the named exceptions, matched by class name along the exception's hierarchy, and every other exception still propagates. The declaration restates the signature B already read, with the result wrapped in `Option`. See [interop](interop.md#a-call-that-can-fail).

For `net:`, the B host has only an explicit set of allowed `System.Math` and `System.Text.RegularExpressions.Regex` methods. The checked-in signature snapshot is compared with live reflection in GitHub CI. The interop transport is typed JSON messages; arbitrary .NET assemblies, custom classes or object identity are not available.

## 6. Diagnostics

| Code | Interpretation |
| --- | --- |
| `E_SYNTAX` | Invalid B grammar |
| `E_REGISTER_VIEW` | The requested source view is unavailable for the declaration or fails its equivalence check |
| `E_SHORTHAND` | An edit row is malformed, lacks a unique parameter or names an unavailable function or parameter |
| `E_SHORTHAND_PENDING` | New compact rows would mix with existing pending source edits |
| `E_HANDOFF` | The proposed conditional edit cannot be applied to the target |
| `E_HANDOFF_CHANGED` | The file changed before the checked revision could be written |
| `E_DEPTH` | Expression nesting exceeds the compiler’s capacity, including long decision chains |
| `E_NAME` | Unknown, duplicated or reserved identifier |
| `E_HISTORY_PREDICATE` | Unsupported operation or type in an ordered predicate |
| `E_TYPE` | Incompatible types or unsupported type syntax |
| `E_ARITY` | Wrong argument count for known function / available overloads |
| `E_OVERLOAD_AMBIGUOUS` | Multiple overloads remain possible with incompatible contracts |
| `E_DIV_ZERO` | Provably zero divisor |
| `E_ASSERT` | Statically disproven assertion |
| `E_IMPORT` | Unresolved import |
| `E_FOREIGN` | Invalid or unauthorized external binding |
| `E_STRICT` | Strict mode refuses unresolved warnings |
| `E_EXTENSION` | Unsupported source filename suffix |
| `E_METADATA` | Metadata inspection/verification failure |
| `W_UNCHECKED_FOREIGN` | Dynamic external method without known signature |
| `W_DYNAMIC_TYPE` | Dynamic value narrowed by a runtime type check |
| `W_RUNTIME_ASSERT` | Assertion known only at run time |

`b check FILE --strict --json` emits `accepted`/`rejected`, diagnostics and the *assumed foreign signatures*. `behavior_proven: false` is deliberate. The execution boundaries in B 0.4 are tested, not mathematically verified.

## 7. Current limitations and status

No B-authored module imports; generic B functions; reassignment; recursive records; general effects/capabilities; exception modeling; asynchronous calls; zero-copy data exchange; Java/Rust/WASM backends; arbitrary .NET libraries; true native B compilation; formal proof or safe execution of untrusted code. `Option` values support a typed `??` fallback, but not yet exhaustive pattern matching/case analysis or unsafe forced unwrapping. Type checking is conservative and may reject useful Python calls; this is safer than silently claiming a type it cannot establish.

## 8. Versioning

Changes to the grammar, types, interop and accepted code must carry tests. The compiler is an experimental, unverified implementation; runtime guard success is not a proof of full functional correctness.

## 9. Typed BIR compilation

The parser still uses the syntax in `syntax.lark`; v0.5 introduced BIR, and v0.6 extends it to **BIR v2** after static checking. The Python backend consumes BIR, not B source directly. `b ir FILE` prints the checked BIR as JSON; `--optimized` shows the conservatively simplified version. The latter may fold pure native literal expressions, but not external functions, dynamic guards or mutable values.

BIR is an internal, typed compiler representation and has no supported *untrusted JSON input* mode. See [BIR specification](bir.md). B 0.6 adds new language-level contract and effect declarations, while preserving the type spellings from v0.4.

## 10. Contracts and effects (B 0.6)

A function can declare `pure`, `requires` and `ensures` (in that order). A `requires` predicate is checked before the function body; an `ensures` predicate sees its typed return value through `result` after the body. Contract expressions are restricted to call-free comparisons and arithmetic. A built-in integer interval analyzer certifies a subset; other clauses remain runtime checks and make strict mode refuse the program. Known false precondition calls, impossible preconditions and provably false postconditions are rejected before execution.

`permit [console, foreign]` must be the first statement; omission keeps the v0.5 default. `pure` rejects foreign calls or unknown mutable global captures, while `permit` constrains program-wide tracked effect categories. **Foreign means potentially arbitrary imported behavior, not a safe network/file permission system.** Full operational rules, verification statuses, limitations and examples are in [contracts-effects.md](contracts-effects.md).

## 11. Adopted Python-source functions (B 0.7)

```
adopt py:b_examples.pure_kernels.square as sq
let result: Float = sq(4.0)
```

Grammar: `adopt_stmt = "adopt", "py", ":", dotted_module_and_function, "as", local_identifier`. The final segment names a single top-level Python function; the preceding segments identify a `.py` source module. `adopt` is **not** the same as `use`: it statically translates a small safe expression subset into an ordinary `fn` in BIR, never imports the Python module at runtime, and treats the resulting function as B-native. It uses explicit Python `int/float/bool/str` annotations as B types and rejects all unsupported syntax. No fallback to unchecked execution exists. See [source adoption specification](source-adoption.md).

`E_ADOPT` signals unsupported source, missing source, ambiguous definitions, effects or unsupported annotations. `b adopt-audit py:MODULE --json` reports eligibility for that narrow subset. The BIR function carries `backend: py-source` and a `target` containing its original source location and SHA-256. No overall behavioral-correctness proof is implied.


## Discovering an integer postcondition

`b discover FILE --function NAME --json` returns an implementation-derived proposal and its evidence. `--expect 'result == ...'` checks a separately supplied equality. `b check` can export an affine result equality to other functions after verifying the declared contract. [Supported expressions, examples and exit codes](contract-discovery.md).


## Clarifying a proposed change

`b clarify FILE REQUEST [--edit REVISED] [--answer JSON] [--json]` checks candidate postconditions and asks about a concrete permitted output on an explicit grid. `--strategy minimax` selects the optional bounded policy-identification planner. [Request format, semantics, abstentions and exit codes](contract-questions.md).


## JavaScript libraries and joint checks

A `js:` import can name an installed npm package or the supported `"node:path/posix"` module. Quote hyphenated and scoped names. [Foreign types and examples](interop.md).

`b check FILE --joint REQUEST` tests a typed relation across pairs of native integer calls in the specified finite domain. Additional `--joint` files can be checked in the same invocation. [Requirements and failure output](joint-checks.md).
