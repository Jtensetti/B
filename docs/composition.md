# Contract analysis across functions

B 0.8 records three kinds of obligation on checked BIR. A native call must meet the target's `requires` clause. A function result must satisfy its `ensures` clause. Division and remainder require a nonzero denominator. The report describes the requirement at the expression site, assuming control reaches it and its operands return normally.

## A count that can become zero

| Obligation | Count guaranteed positive | Count guaranteed nonnegative |
| --- | --- | --- |
| Return at least ten after adding a reserve of ten | proved | proved |
| Divide the total cost by the count | proved | unknown |
| Pass an allowed input to the count function from either caller | proved | proved |

```sh
b impact examples/revisions/count-positive.bee examples/revisions/count-zero.bee --json
b check examples/revisions/count-zero.bee --json
b check examples/revisions/count-zero.bee --strict --require-proofs
```

In these fixtures the changed function actually returns zero on input zero. Weakening its declaration alone yields the same loss of proof even if it still returns a positive count in every execution. A caller may rely only on what the provider promises and the compiler has established.

For an operation defined to return zero when its divisor is zero, pass the computed count to a helper and check the parameter once:

```bee
fn rate(cost: Int, n: Int) -> Float pure = if n == 0 then 0.0 else cost / n
```

A verifier can check this implementation. The choice to return zero for an empty run belongs in the application's specification.

## Reading a report

`b check FILE --json` includes `contract_analysis.obligations`. Each record identifies its caller, structural site, kind, target, requirement and direct dependencies. A dependency names a producer relevant to the expression. To follow an exported guarantee another hop, inspect that producer's own postcondition. The report also includes the rendered expression where available. An empty obligation list can occur in a program without contracts or division.

| Status | Meaning at the site |
| --- | --- |
| `proved` | The available facts establish the requirement. |
| `refuted` | The available facts exclude satisfaction if execution reaches the site with evaluated operands. |
| `unknown` | The facts permit no conclusion. A failing input may or may not exist. |

`--strict` rejects compiler warnings, including outstanding pre- and postconditions. `--require-proofs` rejects every unproved reported obligation, including a possibly zero divisor. The flags can be combined. A gate failure in JSON includes the report. Earlier syntax, type and constant-contract errors still reject the source during compilation. B keeps its runtime contract and type checks in generated code.

## What can cross a boundary

The analyzer computes integer ranges, with a separate fact for a known nonzero integer. It handles simple comparisons, selected arithmetic and conditional paths. Across native calls it uses the independently checked part of a declared integer result range once it can establish the call's precondition. A wrapper's checked contract can then supply facts to its own callers. A declaration supported only by runtime checking cannot supply such a range. A recursive declaration cannot establish itself. Imported signatures describe types and provide no value guarantee.

These are partial-correctness statements over a restricted domain. A nonzero divisor proof says nothing about floating-point overflow, termination or a contract the application forgot to state. B 0.10 can also publish [exact affine result equalities](contract-discovery.md) after checking the complete contract. A reported proof method identifies one analysis used. A conjunctive guarantee can depend on several methods. Repeating a call in a branch condition and in its body is also different from testing a single named value.

## Comparing revisions

`b impact BEFORE AFTER` compiles both files and reports changes. The JSON includes the obligations on both sides so tools can distinguish a weakened contract, a lost proof and a removed operation. A removed obligation may reflect a deleted requirement. Review the changed code and run behavioral tests before interpreting removal as a repair.

Impact first aligns an obligation at the same site with the same expression, then matches an expression that moves uniquely within its caller. Remaining edits can be paired by site. Moved checks are identified in the report. Duplicates and renames can yield added or removed entries.

Sites identify positions in the checked expression tree. They have no identity outside their function or across arbitrary rewrites. Both source revisions must pass the front end. Comparison recomputes both programs in full. Library resolution uses the local Python environment and its trusted import hooks. Dotted `use` lookups inspect filesystem packages without running their initializers.
