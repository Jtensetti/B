# Passing a checked edit to the next maintainer

A pending edit belongs to a named source function. It says exactly when to override its result. The author can leave the program running with today's behavior until another maintainer applies the edit.

```bee
fn route(days: Int) -> Text pure = if days < 3 then "priority" else "standard"
next route when days == 5 => "express"
print route(5)
```

Try it on a copy of the [example](../examples/handoffs/dispatch.bee).

```sh
cp examples/handoffs/dispatch.bee work.bee
b run work.bee
b next work.bee
b next work.bee --apply
b run work.bee
```

The first run prints `standard`. Listing prints only `next route when days == 5 => "express"`. Applying it inserts `if days == 5 then "express" else` before the original body, removes the pending instruction and writes the checked revision to the file. The second run prints `express`. Listing again yields an empty result and applying again leaves the file alone.

If the next maintainer needs to inspect the target, `b next work.bee --context` displays each affected declaration followed by its instruction once. This saves opening the whole file for a small change. The output omits other functions and external requirements. A maintainer may still need those for an unfamiliar change. [Token counts and retrieval comparisons](../experiments/handoff-cost/README.md).

## Compact input

Use `b next PROGRAM --from-short ROWS` to preview a batch, or use `-` for standard input. Each line describes one equality override. The short form is a separate input to this command. Source files continue to support ordinary `next` expressions.

| Row | Meaning |
| --- | --- |
| `route 5 "express"` | When the only parameter of `route` equals 5, return "express". |
| `signal phase 3 8` | When the named parameter `phase` of `signal` equals 3, return 8. |

The comparison value and replacement must both be B scalar literals. Quoted text can contain spaces and literal hashes. For a function with multiple parameters, write the parameter name even when their types differ. The expanded edit is subject to B's existing scope, type and fallback checks. A batch may target several distinct functions. Resolve any earlier pending edits before supplying new rows. `--context` includes the affected declarations. `--apply` applies the complete checked batch to the original file. A failing row leaves the file intact. Repeating an applied batch whose identical edits are still the leading branches leaves the source untouched.

If an exception only applies when `phase == 3 and channel != 0`, write the full expression in the ordinary register. A short row naming `phase` alone would change every channel. [Source token counts](../experiments/shorthand-encoding/README.md) · [First-submission outcomes](../experiments/shorthand-pilot/README.md).

## What is checked

The condition uses the target's parameters, literals, comparisons, Boolean operators and basic arithmetic. Calls to other functions belong in the replacement expression. The condition must produce a Boolean and the result must fit the function. B also checks that the conditional preserves the existing result conversions on the fallback branch. The target must have a B source definition. A file can carry one pending edit per function. Multiple targets are checked together and applied in one file replacement. When any edit fails, the file keeps its original contents.

B checks the current and proposed programs. `b next FILE --strict` and `b next FILE --apply --strict` reject unresolved static warnings. `b check FILE --require-proofs` checks obligations from both revisions. Ordinary `b run` executes the current function. A separate `--joint` request checks the running revision, so apply first to evaluate a proposed interaction between two calls. A subsequent source edit can change the context of the pending request. Applying it checks the file in its current state.

A well-typed instruction can still express yesterday's requirements. Suppose `next signal when phase == 3 => 8` predates a decision reserving channel 0 for diagnostics. As written, it would also change channel 0. To preserve that channel, the pending guard needs `phase == 3 and channel != 0`. The [handoff experiment](../experiments/handoff-pilot/README.md) includes this distinction. A lasting behavioral requirement belongs in a test or contract that later changes must also satisfy. Record the reason in the product brief when it affects future decisions.

## Upgrading B 0.13 source

B 0.14 treats free-form `#` comments as a syntax error, including on the older supported source suffixes. A hash in a quoted string, such as `"#336699"`, remains part of the value. To copy a legacy file without comments, use a **different output path**.

```sh
b migrate-comments old.bee > converted.bee
b check converted.bee
```

The migration is lexical. It preserves quoted hashes, escapes and line endings. It can copy partially written source. Check the output before using it. Migration removes prose. Read old notes before discarding the original if they might contain a decision you still need.
