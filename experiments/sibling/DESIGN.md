# Design: the sibling trials

This is the plan for measuring the [goal](../../docs/vision.md#long-term-goal). Each trial gets its own pre-registration, committed before any solver runs. This file fixes what every trial shares.

## The world every task lives in

Each task comes with **five small libraries, one per ecosystem**: a Python module, an npm package, a Go module, a Rust crate and a C# project. They are written for the task, are 40–120 lines each, and are what a company would actually have: a tariff table maintained by one team in Go, a geometry crate in Rust, VAT rules in C#. Every task needs at least three of them.

A solver in language X gets the same five libraries. It can call the one in its own ecosystem directly. The others it must port, wrap or call as a subprocess, as a team working in X alone would. B calls all five through its adapters. This is exactly the situation B claims to handle better, and it is measured, not assumed: if porting is cheap and safe for models, B loses on work and errors.

## Languages and solvers

B, typed Python (checked with mypy --strict), C#, TypeScript (checked with tsc --strict), Go and Rust. Three Claude Haiku solvers per language and task, each in its own workspace.

## Protocol

Each solver runs the whole trial in one agent run. It gets the build brief and is told to run `next` when a step is done. `next` snapshots the workspace for grading and prints the next change, or END. The solver cannot see later changes. Specifications are complete, and there are no questions.

## Measures

- **Errors (condition 2):** each snapshot is run on hidden fixtures, and wrong outputs are counted per step, summed over the build and the changes.
- **Work (condition 3):** output tokens of the whole agent run, from its transcript.
- **Faults (condition 4):** a separate pre-registration. Seeded faults at the library borders are applied to every finished program, and the question is whether the language's own build step (b check, mypy --strict, tsc --strict, dotnet build, go vet, cargo build) stops the program before it runs.

## Rules that do not change between trials

- A trial is not re-run or re-graded to change its result. A grading or oracle bug is fixed only under the rule in the trial's pre-registration, and the fix is reported.
- B's guide for models is frozen at the commit of each pre-registration.
- Results go below the line in each pre-registration, whatever they are.

## Which tasks count (fixed before task C)

Conditions 1–3 of the goal are judged on exactly three tasks: A, B and C. No task is added, re-run or dropped to change the sums, whatever A and B showed. Task C uses the same scale as A and B: five libraries of 40–120 lines each, a build and five changes. B may improve between tasks. Each task records the B version it ran, and every task's result counts as measured.
