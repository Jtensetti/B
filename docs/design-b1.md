# B 1.0 — language design proposal (NOT implemented)

**Status:** Research design for a future version, separate from the verified v0.1 grammar. No examples below should be represented as accepted B v0.1 programs.

## What makes B different?

B would be a *polyglot-first, contract-bearing, representation-independent language*. Its defining feature is not a new spelling of Python expressions. It is that modules from foreign ecosystems become typed, versioned and costed operations in one B program. B's own language semantics must not depend on guessing what foreign code means.

A successful B program should be able to express a computation, declare what it assumes and what it guarantees, import functionality from several ecosystems, and choose implementations through explicit constraints. The compiler can then reject invalid combinations or demand additional evidence **without pretending that inferred assumptions are proofs**.

## Proposed language surface

```text
# Illustrative future syntax, NOT executable in B v0.1.
use py:pandas @ "2.x" as pd      # resolved to a locked version
use net:System.Math as math       # CLR adapter
use wasm:acme/image@1 as image   # component ABI

record Measurement {
    value: Float64
    unit: Unit
}

type Outcome[T] = Ok(T) | Err(Text)

fn normalize(xs: List[Float64]) -> Outcome[List[Float64]]
    requires len(xs) > 0
    ensures result is Ok => every(result.value, finite)
    effects pure
= {
    let max_value = max(xs)
    if max_value == 0.0 then Err("zero scale")
    else Ok(xs.map(x => x / max_value))
}
```

The surface syntax is illustrative only. An actual language spec must define binding scope, implicit conversions, nullability, evaluation order, errors, generic variance, effects, ownership and name resolution before anything here is implementable.

## Canonical program graph rather than one text format

B can have three distinct representations which are **semantically equivalent**:

1. **Readable view** for people and existing coding models.
2. **Compact model view** with stable operation IDs and references to already typed values. A model need only provide information that cannot be inferred from context.
3. **Canonical IR** storing operation IDs, versioned types, effects, contracts, origins and dependencies. This is the program of record.

Changing the presentation must not change the meaning. An IR node must have stable identity so that small edits can be expressed and checked without regenerating unrelated code. But context and library availability are not free: we should benchmark all bytes, tokens and computation involved.

## Formal core: what must eventually be specified

### Values and types

Types should distinguish `Bool`, signed and unsigned fixed-width integers, arbitrary integers, floats with explicit widths, decimal, UTF-8 text, bytes, arrays and vectors, records, variants, `Option[T]`, `Result[T,E]`, callable types and handles to foreign resources. Units/dimensions are valuable where relevant, not mandatory for every number.

A conversion must specify whether it is exact, checked, saturating or lossy. In particular, large B integers cannot silently become foreign 32-bit integers, and a foreign `null` cannot silently become an ordinary B value.

### Effects

Every function should declare or infer effects such as `pure`, `io`, `fs.read`, `fs.write`, `network`, `foreign` and `nondeterministic`. The system must not silently classify a foreign function as pure without evidence. B may permit effectful functions, but permissions must be explicit.

### Ownership and resources

A borrowed foreign view, an owned copied value and a remote process handle are different kinds of resources. Their lifetimes must be tracked. Never promise zero-copy unless the buffer ownership, alignment, numeric representation and concurrency rules justify it.

### Behavioral contracts

Contracts should be able to express preconditions, postconditions, invariants and resource bounds. A verification result must always identify *which property* was proved and under *which assumptions*. `unknown` is a first-class outcome; it may block strict builds.

### Concurrency

Tasks and message streams should have explicit ordering, cancellation and delivery semantics. Messages and resources may be shared only through declared interfaces. Concurrency cannot inherit undefined execution semantics from multiple host languages.

## Foreign library import pipeline

```text
Package / assembly / component
  -> native metadata, stubs, WIT or manually signed declaration
  -> generated B interface with source and version
  -> static type / effect / capability checks
  -> runtime adapter with checked marshalling
  -> optional proof and behavioral tests
```

The binding generator needs **provenance**, a lockfile, a reproducible adapter generator version, signatures, effect information, compatible platforms and explicit trust tier. A generated signature is not proof that a package's code is sound.

## Trust levels of an operation

- `verified-core`: correctness against B's formal core rules.
- `runtime-guarded`: boundary type contract enforced on actual values, behavior assumed.
- `unverified-foreign`: usable only when policy permits; must be visible in reports.
- `proved-behavior`: specific theorem established by a proof checker and linked to the actual versioned implementation.

Strict policies should allow selecting the minimum tier for selected modules and effects. They must not grant universal correctness by default.

## The hardest interoperability question

If B executes a call to Python and another to .NET, who owns the values, who can mutate them, and what does it cost to move them? A universal call syntax alone does not answer any of this. The performance breakthrough may come from **placing computations near data** and composing coarse-grained library calls, not from a cheaper spelling of arithmetic operators.

A cost model should compare copying/serialization, crossing process boundaries, shared memory, startup, JIT, garbage collection and model tokens. This is where B might be materially better than conventional cross-language bridges.

## Research milestones that could falsify B

1. B cannot outperform a strong Python.NET/GraalVM/Wasm composition baseline in relevant workloads.
2. Binding metadata is too incomplete to offer meaningful checks for real packages.
3. A model reliably generates more correct native Python/C# code than B code even when budgets are matched.
4. The canonical IR is more expensive to create and maintain than it saves in iterative edits.
5. Foreign process, serialization or allocation costs dominate the useful computation.

If these failures persist across carefully controlled tests, B should narrow its ambitions to domains where it actually excels — or be discontinued. **A new language is justified by evidence, not by novelty.**
