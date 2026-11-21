# Benchmark plan — price of a correct program

The correct objective is not the fewest characters, the fewest prompts or even the fewest input tokens. It is **total compute and engineering cost per correct result**, with explicit quality, latency and safety constraints.

## Proposed experiments

1. **Cross-language composition:** B vs Python.NET vs a C#/Python sidecar vs WebAssembly components for matching use cases; include cold start, warm call, serialization, errors, array throughput and memory overhead.
2. **Language generation:** same model, tasks, retrieval access and budget, generate B and Python/C#. Score actual independent behavior and not merely syntax or pass rate on known tests.
3. **Change resilience:** provide a sequence of feature changes. Track regressions, unwanted edits, accepted tests, tokens, attempts and total end-to-end cost.
4. **Verifier value:** compare checking during generation against compile-test-repair afterwards, controlling for the total budget. Count false positives, false negatives and unknown results explicitly.
5. **Library coverage:** percent of a version-pinned corpus of real PyPI/NuGet symbols whose signatures can be represented and executed safely, not just the number of modules importable.

## Measurement requirements

- Freeze model version, tokenizer, prompt, temperature, runtime, hardware and library versions.
- Use independent hidden tests for correctness and manually audited specifications for a sample.
- Report compile-time, run-time and total time, model input/output tokens, number of repairs, runtime errors and failed foreign boundaries.
- Compare B to **strong** baselines with the same testing and tool budget.
- Include time and cost of creating an adapter or native wrapper where relevant.
- Split results by problem type, library family, codebase size and need for foreign calls.

## Status

**No performance or AI-token benchmark has been run yet.** The included tests establish only that the implemented subset behaves as expected in the covered cases. Treat all efficiency claims as unproven until measured.
