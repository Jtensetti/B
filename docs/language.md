# B language reference — implemented experimental v0.2

**Status:** This is the specification for the supported v0.2 subset. It is not a specification for a future universal B. Actual parser rules are in [`b_lang/syntax.lark`](../b_lang/syntax.lark); divergence between specification and compiler is a bug to be tested.

## 1. Source and lexical rules

- Source is UTF-8 text. File suffix `.bsrc` is preferred; `.b` is supported for v0.1 compatibility.
- Comments begin with `#` and last until the end of the line.
- A newline terminates a statement. A semicolon is not a statement separator. Whitespace between tokens is ignored; there are no indentation-based blocks.
- Identifiers match `[A-Za-z_][A-Za-z0-9_]*`. Names beginning `_b_` are reserved for runtime internals.
- Integers are base-10 digits with no leading zeros except the digit `0`; negative values use a unary `-` operator. Decimal floats require digits on both sides of `.`. No exponent literals yet.
- Strings use JSON-compatible double-quoted escaped text. Literal keywords are `true`, `false`, `none`.
- The parser reports errors rather than silently guessing symbol replacements.

## 2. Grammar

Informative EBNF simplified from the implemented parser. B v0.2 source includes top-level statements and expressions:

```ebnf
program       = { newline | statement, newline }, [statement] ;
statement     = use | foreign | let | fn | print | assert ;
use           = "use", ("py" | "net"), ":", path, "as", identifier ;
foreign       = "foreign", path, "(", [type_list], ")", "->", type ;
let           = "let", identifier, [":", type], "=", expression ;
fn            = "fn", identifier, "(", [parameter_list], ")", "->", type, "=", expression ;
print         = "print", expression ;
assert        = "assert", expression ;
parameter     = identifier, ":", type ;
type_list     = type, {",", type} ;
path          = identifier, {".", identifier} ;
type          = identifier, ["[", type, {",", type}, "]"] ;
expression    = "if", expression, "then", expression, "else", expression
              | logical_expression ;
```

The remaining expression precedence, highest first: attribute access/call, unary `not`/`-`, `*`/`/`/`%`, `+`/`-`, comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`), `and`, `or`. Parentheses group expressions; list literals use `[...]`. The conditional `if ... then ... else ...` is an expression with lower precedence than `or`; parentheses allow embedding it within arithmetic. Nested `if` expressions associate with the closest `else` following the parser rules.

`use` binds a module alias. The source path may contain dots. `foreign` must follow a corresponding imported `py:` alias and declare a member's positional parameter types and return type; aliases and names cannot be redefined. Declarations for arbitrary .NET methods are not supported: the host must explicitly allowlist those methods first.

## 3. Types

| Type | Runtime representation in current Python backend |
| --- | --- |
| `Int` | Python integer (unbounded), excluding booleans |
| `Float` | Finite Python float. Integer arguments and JSON number representations are normalized to Python `float` at typed boundaries; native arithmetic follows Python numeric rules |
| `Bool` | Python `True`/`False`, not assignable to `Int` |
| `Text` | Python Unicode string |
| `List[T]` | Python list with members checked against `T` at annotated boundaries |
| `Any` | An explicitly dynamic type; not a proof of correctness |
| `None` | Internal inferred type for `none`; not a permitted declared type |

Type assignability is identity plus `Int` → `Float`, dynamic `Any` (with runtime checks when narrowed), and element-wise `List[T]` compatibility. Inferred heterogeneous lists may have `List[Any]`; narrowing them to `List[Int]` triggers a runtime element check, even when `Any` is nested. Typed lists are copied and their elements normalized at runtime boundaries. Converting an out-of-range `Int` to `Float` raises a boundary error; in-range conversion may round. In strict mode such unresolved dynamic checks are rejected.

Expressions in an `if` must have compatible branch types; when the branches are `Int` and `Float`, the inferred type is `Float`. A known condition selects the known branch for constant propagation. Both branches are type-checked, whether or not the condition is statically known. When no common non-dynamic type can be established, a known-type mismatch is an error.

## 4. Evaluation

- Top-level `let` values are assigned once in order. B v0.2 has no reassignment statement.
- `fn f(x: T) -> R = expression` declares an expression-bodied function with positional typed arguments. The return value is guarded against `R`. Calls must match known arity and types. Termination of recursive functions is not established.
- Arithmetic, comparison and logic follow the current Python backend's semantics. `and` and `or` short-circuit. `if condition then yes else no` evaluates only the selected branch at runtime.
- `print value` prints the value and a newline.
- Division by an expression known to be zero is rejected by `E_DIV_ZERO`. Unproven denominators are not generally checked statically; at runtime ordinary Python divide-by-zero behavior applies.
- `assert expression`: a statically false constant assertion causes `E_ASSERT`; a statically true one is accepted. Other assertions remain runtime obligations and generate `W_RUNTIME_ASSERT`; `--strict` rejects the warning. Runtime assertions are explicit exception-raising code, not Python `assert`, so Python optimization does not disable them.
- Floating-point behavior currently inherits Python semantics, and some numerical overflow/underflow cases are not exhaustively specified. Arbitrary integer size and cross-runtime conversion policies require future revision.

## 5. Imports, signatures and foreign assumptions

```text
use py:json as json
foreign json.dumps(List[Int]) -> Text
let encoded: Text = json.dumps([1, 2, 3])
print encoded
```

B calls the *real* installed `json.dumps` function. The declaration supplies a **trusted boundary contract**: B checks the argument list type before calling, and checks that the returned value is `Text`. It does not prove that `json.dumps` implements the expected JSON semantics. If the declaration lies, the runtime guard may catch a type mismatch but cannot generally detect an incorrect value of the correct type.

Unknown Python symbols are dynamic and produce `W_UNCHECKED_FOREIGN`. Built-in typed signatures exist for a few `statistics` and `math` functions. B v0.2 uses a .NET 10 JSON-lines host with allowlisted `System.Math` methods and `System.Text.RegularExpressions.Regex.IsMatch(Text,Text)->Bool` (with a 250 ms regex matching timeout). The host rejects arbitrary method names, type mismatches and non-finite numeric results.

A foreign declaration is listed under `assumed_foreign_contracts` in `b check --json`. Strict checking means no unresolved static warnings; it is **not** a guarantee that foreign behavior was proved.

## 6. Error codes

| Code | Meaning |
| --- | --- |
| `E_SYNTAX` | A source file does not follow B grammar |
| `E_NAME` | Unknown, repeated or reserved identifier |
| `E_TYPE` | Invalid type or incompatible typed values |
| `E_ARITY` | Wrong number of arguments to a known function |
| `E_DIV_ZERO` | A divisor is statically known to be zero |
| `E_ASSERT` | A statically known assertion is false |
| `E_IMPORT` | An import cannot be resolved |
| `E_FOREIGN` | Foreign binding invalid, duplicated or not allowlisted |
| `E_STRICT` | An unresolved warning remains in strict mode |
| `E_EXTENSION` | File extension is not `.bsrc` or legacy `.b` |
| `W_UNCHECKED_FOREIGN` | Unknown dynamic Python symbol/call |
| `W_DYNAMIC_TYPE` | A runtime type check is needed when narrowing dynamic data |
| `W_RUNTIME_ASSERT` | An assertion has not been proven statically |

`b check --json` returns `status`, version, diagnostics and trusted foreign assumptions. It never reports full behavioral correctness as proven. Errors cause a nonzero exit status. There is no full machine-checked proof system in the current version.

## 7. Not implemented

General native machine code generation; B-authored modules; loops; mutable bindings; user records; generic B functions; richer algebraic types (`Option`, `Result`); Python type-stub ingestion; broad CLR reflection; Java, Rust and WebAssembly interoperability; effect inference; asynchronous programs; multi-agent operations; isolation of untrusted programs; formal behavioral proofs.

## 8. Versioning

This specification describes the implemented v0.2 **subset**. Compiler changes must carry tests and docs. Nothing here gives a guarantee about a foreign library's internals, an untrusted user's Python code or indefinite future runtime environments.
