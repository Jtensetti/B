# B language reference — implemented experimental v0.13

This document specifies **the implemented subset**, not the eventual B 1.0 ambition. The authoritative executable grammar is [`b_lang/syntax.lark`](../b_lang/syntax.lark), and the static type system is implemented in [`b_lang/types.py`](../b_lang/types.py) and [`b_lang/compiler.py`](../b_lang/compiler.py). Where this document and the compiler differ, that is a bug to fix and test.

For source adoption and contract analysis across functions, see [source adoption](source-adoption.md), [contract analysis](composition.md) and [conditional guarantees](conditional-guarantees.md).

## 1. Source form and tokens

B source is UTF-8. **`.bee` is the recommended extension**; `.b4` is an optional playful alias, with `.bsrc` and `.b` retained for compatibility. `.bi` is *not* adopted: FreeBASIC already uses it for headers. `.b4` also has a historical non-B use and is not reserved. The CLI validates the file contents regardless of suffix.

A newline separates top-level statements. Inside a `cases` table, rows can occupy separate lines or share a line using semicolons. Blank lines and `#` comments are ignored. Identifiers match `[A-Za-z_][A-Za-z0-9_]*`; `_b_` is reserved for compiler internals. Strings are JSON-compatible double-quoted literals. Integers have decimal notation; floating literals have a decimal point; negative values use unary `-`. No exponent literals or arbitrary Unicode identifiers yet. Whitespace between tokens is ignored.

## 2. Grammar

The following EBNF captures the implemented constructs; the Lark grammar governs exact precedence and parsing:

```ebnf
program       = { newline | statement, newline }, [statement] ;
statement     = permit | use | adopt | foreign | let | fn | print | assert ;
permit        = "permit", "[", [identifier, {",", identifier}], "]" ;
use           = "use", (("py" | "net"), ":", path | "js", ":", (path | string)), "as", identifier ;
adopt         = "adopt", "py", ":", path, "as", identifier ;
foreign       = "foreign", path, "(", [type_list], ")", "->", type ;
let           = "let", identifier, [":", type], "=", expression ;
fn            = "fn", identifier, "(", [parameters], ")", "->", type,
                ["pure"], ["requires", expression], ["ensures", expression], "=", expression ;
print         = "print", expression ;
assert        = "assert", expression ;
parameters    = parameter, {",", parameter} ;
parameter     = identifier, ":", type ;
type_list     = type, {",", type} ;
type          = identifier, ["[", type, {",", type}, "]"] ;
expression    = "if", expression, "then", expression, "else", expression
              | coalesce_expression ;
coalesce_expression = logical_expression, ["??", coalesce_expression] ;
list          = "[", [expression, {",", expression}], "]" ;
dictionary    = "{", [pair, {",", pair}], "}" ;
pair          = expression, ":", expression ;
case_table    = "cases", identifier, "{", {newline}, row, {row},
                "else", "=>", expression, [";"], {newline}, "}" ;
row           = comparison_operator, scalar_threshold, "=>", expression, separator ;
separator     = ";", {newline} | newline, {newline} ;
```

A case table is an expression. It compares the named value against each scalar literal in order, using the ordinary comparison operators and type rules. The first matching row supplies the result, with a mandatory final fallback. Numeric thresholds can be negative. See [decision tables and source views](registers.md).

Expressions also allow literals (`true`, `false`, `none`, numbers, strings), references, calls, attribute access and grouping. Precedence (highest to lowest): postfix attribute/call, unary `not`/`-`, multiplication/division/modulo, addition/subtraction, comparison, `and`, `or`, `??` (right associative), conditional. Both conditional branches are statically type-checked, even if the condition is constant.

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

For `net:`, the B host has only an explicit set of allowed `System.Math` and `System.Text.RegularExpressions.Regex` methods. The checked-in signature snapshot is compared with live reflection in GitHub CI. The interop transport is typed JSON messages; arbitrary .NET assemblies, custom classes or object identity are not available.

## 6. Diagnostics

| Code | Interpretation |
| --- | --- |
| `E_SYNTAX` | Invalid B grammar |
| `E_REGISTER_VIEW` | The requested source view is unavailable for the declaration or fails its equivalence check |
| `E_DEPTH` | Expression nesting exceeds the compiler’s capacity, including long decision chains |
| `E_NAME` | Unknown, duplicated or reserved identifier |
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

No B-authored module imports; generic B functions; loops; reassignment; records; general effects/capabilities; exception modeling; asynchronous calls; zero-copy data exchange; Java/Rust/WASM backends; arbitrary .NET libraries; true native B compilation; formal proof or safe execution of untrusted code. `Option` values support a typed `??` fallback, but not yet exhaustive pattern matching/case analysis or unsafe forced unwrapping. Type checking is conservative and may reject useful Python calls; this is safer than silently claiming a type it cannot establish.

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
