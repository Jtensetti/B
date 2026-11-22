# B roadmap — evidence before promises

B is an independent language with a parser, type checker and Python-AST lowering, plus explicit foreign adapters. The target is fewer model-generated decisions and greater verified capability per token/cost, while reusing existing ecosystems. No AI programming benchmark has yet confirmed this advantage.

## B 0.11

[Contract clarification](contract-questions.md) can distinguish supplied policies or ask only about the outputs of a pending edit. On the [paired comparison](../experiments/intent-pilot/README.md), typed Python and plain-language questions matched B. On the [complete three-row layout problem](../experiments/layout-coherence/README.md), single-return contracts cannot distinguish an independently adjustable layout from one that requires a consistent style.

For 0.12, test one joint requirement over two calls from the same version. Compare its cost with passing a shared style parameter, checking a whole layout as one value, and using a two-call typed Python property test. Measure valid style changes retained and mixed layouts wrongly accepted. Let the specification's natural scope decide whether a new language feature earns its place.

## B 0.10

B can [discover and independently check a candidate equality](contract-discovery.md). The [contract pilot](../experiments/contract-pilot/README.md) found that eight AI solvers on two explicit maintenance tasks reached the same correctness ceiling with and without discovery. Copying a verified current default into a contract can still reject legitimate future implementations.

A direct symbolic read derived the three pilot/example identities without observations and also handled `2*x`. Reserve the cost of probing for concrete disagreements or properties the symbolic pass cannot decide.

The next proposed experiment gives the model two plausible policies that accept the current program. Let it ask about a single alternative output on which those policies disagree. Compare that intervention with a plain-language clarification, a passive list of facts, and a typed Python tool with the same information. Score the downstream edits each contract admits or blocks, the cost of the extra interaction, and outcomes on unseen tasks. If a matched Python tool yields the same results at lower total cost, put the next implementation effort there.

## B 0.9

The compiler supports a [bounded fragment of conditional integer guarantees](conditional-guarantees.md). On the same checker a rule can be switched off, and optional repair guidance switched on. The [maintenance pilot](../experiments/law-pilot/README.md) exercises both interventions. A [separate correspondence experiment](../experiments/operator-correspondence/README.md) asks which input is most informative when several interpretations of an operation agree on familiar examples.

A candidate next experiment is to start with competing contracts inferred from examples, choose an input that separates them, and send the surviving candidate to the verifier. Measure how often this finds a useful contract, the cost of unsuccessful proposals and the frequency of missing the true rule when the candidate family is too narrow.

## B 0.8

- [x] Track checked integer guarantees across native calls. Compare obligations between working revisions and identify a lost divisor proof separately from callers whose guarantees still hold.

The [billing pilot](../experiments/change-pilot/README.md) found two correct repairs. Guarding the actual count makes both division proofs pass in 0.8. Guarding the original input also passed the behavior oracle. Its unresolved proof motivated the conditional-guarantee experiment in 0.9.

- [ ] Measure AI-assisted changes over a varied set of held-out tasks, with the same B compiler and richer diagnostics shown or hidden, and a typed Python comparison. Include specification-only edits, genuine regressions and harmless refactors. Count the cost of creating and maintaining the contracts and the cost of failed runs.
- [ ] Compare the same contract diagnostics exposed as a Python tool. The result bears directly on the value of a separate language.

## Implemented through B 0.7

- [x] Experimental `adopt py:MODULE.function as name`: convert an annotated single-expression Python source leaf into a pure, checked native B function, without runtime module imports. Record exact source SHA-256 in BIR.
- [x] `b adopt-audit py:MODULE --json`: show supported and unsupported functions; honest 0/20 on standard-library `statistics`.
- [ ] Expand safe source adoption only when semantics can be defined precisely (nested calls, richer types, contracts).
- [ ] Compare source adoption against Python interop and ordinary B code on held-out AI programming tasks, including costs.

- [x] B syntax, AST, expression-bodied functions, immutable bindings, operators, lists, conditionals.
- [x] `Option[T]` and `Dict[Text,T]` with literals/inference and recursive runtime type guards.
- [x] Typed lazy `??` fallback; its left operand executes once even when it is a foreign call.
- [x] Reject known heterogeneous collection values before running (rather than delaying to dynamic checks).
- [x] Conservative Python `.pyi`/`.py` AST signature extraction, trailing defaults and two-or-more `@overload` declarations.
- [x] Reject ambiguous overload resolution instead of guessing a result type.
- [x] Real Python imports and explicitly permitted .NET Math/Regex methods.
- [x] Runtime boundary value guards, metadata provenance, JSON diagnostics, strict-mode preflight checks.
- [x] B polyglot and negative tests, Python 3.11/3.13 + .NET 10 GitHub CI.
- [x] `.bee` canonical, `.b4` optional, `.bsrc`/`.b` backward compatible.

## Next: coverage with honest static information

- [ ] `Result[Ok, Error]`, records and stable object/resource reference semantics.
- [ ] Keyword arguments, Python typing overload rules and more of typeshed (`Sequence`, `Iterable`, `Literal`, `Protocol`, selected generics).
- [ ] .NET generic signatures and permission-scoped metadata adapters for selected real packages.
- [ ] Versions/lockfiles and explicit dependency/version provenance for metadata; cache signatures by version.
- [x] Typed BIR v2 as common semantic representation, consumed by Python backend; JSON inspection and conservative native constant optimization.
- [ ] Additional lowering backends, stable IDs and independently verified BIR loading.
- [x] Build a reproducible, narrowly defined direct-signature coverage audit, report negative results on NumPy/pandas/SciPy.
- [ ] Improve real-world library coverage and measure more of the *public API*, including re-exports, classes and methods.

## Later: guarantees and machine efficiency

- [x] Conservative `pure` and `permit` effect classification for native and foreign operations; imports remain broad and untrusted.
- [ ] **Fine-grained**, enforceable effect capabilities and bounded resource use for imported operations.
- [x] `requires`/`ensures` with runtime enforcement and soundly bounded Int interval proofs.
- [ ] General specified invariants with a separately checkable proof/verification kernel.
- [ ] Incremental checking and compilation of versioned program IR nodes; local edits that preserve unaffected code.
- [ ] Other runtimes through real adapters (Rust/C ABI, JVM, WASM Component Model/WIT).
- [ ] Controlled AI benchmark: B vs Python/C#/Rust with matched model, library access, tokens, runtime, retries and correctness tests.
- [ ] Constrained decoding and compact machine-facing representation only after measuring performance.

## Things B does *not* establish

- Any imported library is functionally correct merely because it has a type stub.
- All Python annotations, overloads, and .NET assemblies are understood by B.
- Strict checks guarantee the user's intended behavior or side-effect safety.
- Fewer source characters automatically mean fewer model tokens or lower total cost.

## Research after BIR

See [research directions](research-directions.md) for falsifiable proposals spanning effect systems, machine-checkable contracts, dimensional types and incremental compilation. These are hypotheses, **not implemented language features**.

B 0.6 tracks a **limited effect inventory** rather than installing a real OS-level capability system. See [contracts and effects](contracts-effects.md).
