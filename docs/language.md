# B language specification — experimental v0.1

This document is **normative for the small implemented subset** and explicitly non-normative for any future feature. Parser details are defined in [`b_lang/syntax.lark`](../b_lang/syntax.lark). When this prose and parser diverge, treat the implementation as a bug, not as permission to silently change the language.

## 1. Lexical conventions

1. Source files are UTF-8 and conventionally end in `.b`.
2. Source uses ASCII identifiers `[A-Za-z_][A-Za-z0-9_]*` in v0.1; Unicode identifiers are not yet supported.
3. `#` begins a comment ending at the next newline.
4. Whitespace around expressions is ignored except **newlines terminate statements**. There are no semicolons or indentation-sensitive blocks in v0.1.
5. Integer literals are decimal, nonnegative, without leading zeros except `0`. Decimal real literals require digits before and after `.`. Scientific notation is not available yet.
6. Text literals use JSON-compatible double-quoted strings, including valid JSON escapes.
7. The reserved word literals are `true`, `false`, `none`.
8. An error in these rules is a syntax error; the compiler does not guess a replacement.

## 2. Concrete syntax

Simplified EBNF (the source grammar is definitive):

```ebnf
program      = { newline | statement newline }, [statement] ;
statement    = import | binding | function | output | assertion ;
import       = "use", ("py"|"net"), ":", dotted_name, "as", identifier ;
binding      = "let", identifier, [":", type], "=", expression ;
function     = "fn", identifier, "(", [parameters], ")", "->", type, "=", expression ;
output       = "print", expression ;
assertion    = "assert", expression ;
parameters   = parameter, {",", parameter} ;
parameter    = identifier, ":", type ;
type         = identifier, ["[", type, {",", type}, "]"] ;
dotted_name  = identifier, {".", identifier} ;
expression   = literal | identifier | list | group | attribute | call
               | unary | arithmetic | comparison | boolean ;
```

The `type` shorthand above is descriptive; the actual grammar uses comma-separated type arguments. The current implementation only admits one argument for `List`, and no arguments for primitive types.

**Operator precedence, highest to lowest:** attribute/call; unary `not`/`-`; `*` `/` `%`; `+` `-`; comparisons; `and`; `or`. Binary arithmetic and boolean operators associate left; comparisons permit chaining in the grammar, but chaining currently has ordinary pairwise syntax-tree behavior and should not be relied on as a mathematical chain.

## 3. Types

| Type | Meaning |
| --- | --- |
| `Int` | Python arbitrary-precision integer, excluding `Bool`. This is a v0.1 runtime detail; a future platform-neutral representation needs an explicit size policy. |
| `Float` | Python binary floating-point; `Int` may be accepted where `Float` is expected. Non-finite values are rejected at typed runtime boundaries. |
| `Bool` | `true` or `false`; never interchangeable with `Int`. |
| `Text` | Unicode string. |
| `List[T]` | List of values assignable to `T`. |
| `Any` | Dynamic boundary or explicitly untyped value; does **not** imply verification. |
| `None` | Inferred type of the `none` literal only; not allowed as a variable annotation in v0.1. |

B bindings are single-assignment at top level, with no mutation statement in v0.1. A function has typed parameters and an explicit result type. Functions have a single expression body. Recursive function calls are permitted; termination is **not** proven.

Assignments are type-checked. For example:

```b
let width: Float = 5
let values: List[Int] = [1, 2, 3]
fn hypotenuse(a: Float, b: Float) -> Float = (a * a + b * b) / 2.0
```

`Int` to `Float` is allowed at a typed boundary; other implicit numeric conversions are not defined. List literals containing mixed types can infer `List[Any]`; explicit annotations on literals are checked element-by-element. B's type system is intentionally incomplete and currently lacks `Option`, records, algebraic data types, user classes and generics beyond lists.

## 4. Expressions and evaluation

- Literals evaluate to their values; lists are evaluated from left to right.
- Names resolve to a preceding binding or a function definition; unknown names fail static checking.
- Arithmetic uses Python numeric operations in v0.1. `/` always has static result type `Float`. Constant division by zero is rejected before execution.
- Comparisons produce `Bool`; incompatible known types are rejected. `and` and `or` short-circuit as Python boolean expressions. `not` requires a Boolean.
- A function call evaluates its arguments left to right and evaluates the function body with parameters bound to these values.
- `assert e`: when `e` can be computed by the current static constant evaluator and is false, compilation fails. Otherwise the condition is emitted as a runtime obligation; `--strict` rejects an unresolved obligation. Python `-O` does not remove B assertions.
- `print e` writes a textual representation of the value, followed by a newline.

Constant evaluation currently covers literal arithmetic/boolean expressions and references to constant B `let` bindings. It is intentionally **not** a theorem prover and does not evaluate imported libraries during the check.

## 5. Imports

`use py:module as name` binds a Python module imported by the installed Python interpreter. Checking existence does not validate all module behavior.

`use net:System.Math as name` binds the .NET `System.Math` adapter. The five currently supported methods are `Sqrt`, `Pow`, `Abs`, `Min`, `Max`, with the signatures listed in [`b_lang/types.py`](../b_lang/types.py).

Other Python symbols can be used dynamically with warning `W_UNCHECKED_FOREIGN`; .NET members are fail-closed unless explicitly registered. `b check --strict` rejects all unresolved warnings, but **does not** prove the imported implementation obeys its declared contract.

## 6. Diagnostics

| Code | Description |
| --- | --- |
| `E_SYNTAX` | Invalid B source syntax |
| `E_NAME` | Unknown or redefined binding, or reserved runtime name |
| `E_TYPE` | Incompatible type or invalid type declaration |
| `E_ARITY` | Known function called with wrong number of arguments |
| `E_DIV_ZERO` | Constant division by zero detected |
| `E_ASSERT` | Assertion statically disproved |
| `E_IMPORT` | Python module unavailable or invalid backend |
| `E_FOREIGN` | .NET member not in the allowlisted registry |
| `E_STRICT` | An unresolved diagnostic exists in strict mode |
| `W_UNCHECKED_FOREIGN` | Python call without a registered static signature |
| `W_DYNAMIC_TYPE` | A dynamic value is used where a known type is required; runtime guard inserted |
| `W_RUNTIME_ASSERT` | Static checker cannot establish the assertion; runtime check emitted |

## 7. Intentionally absent

No loops, mutable objects, modules authored in B, asynchronous tasks, records, closures, generics other than `List[T]`, exception handling, concurrency, effects, macros, external process isolation, user-defined foreign signatures or native binary output in v0.1. Adding any of these requires a separate revision of the grammar, typing rules and executable tests.

## 8. Compatibility and versioning

Source behavior is only defined for the implemented `v0.1` subset. Semantic changes require a versioned spec and conformance tests. Foreign-library behavior depends on environment versions and is not covered by B's current static guarantees.
