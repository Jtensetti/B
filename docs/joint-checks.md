# Check the relationship between two calls

Start with the failure an individual call cannot expose. A layout chooses its style once per screen. At every row the gap can be either the rank plus one or the rank plus two. Mixing the choices on one screen produces a broken layout, even though every row has a legal value.

```sh
b check examples/intent/layout.bee --joint examples/intent/uniform.json
b check examples/intent/compact.bee --joint examples/intent/uniform.json
```

The first program passes all three selected pairs. For the second the checker shows `gap(rank=0) -> 2` and `gap(rank=1) -> 2`. After subtracting the ranks the offsets are 2 and 1. This gives a maintainer a specific repair target. If one assembler controls the complete screen, it can instead choose the style once and pass it to each row.

## A requirement file

```json
{
  "left": {"function": "gap", "axes": {"rank": [0, 1, 2]}},
  "where": "left_rank < right_rank",
  "ensures": "left_result - left_rank == right_result - right_rank"
}
```

`right` defaults to `left`. Supply a second function and its input axes to relate distinct operations, such as a row's end and the next row's start. `where` defaults to true and may refer only to inputs. `ensures` may also use `left_result` and `right_result`. Predicates use a bounded subset of B's integer arithmetic, comparisons and Boolean operators. All argument axes are explicit. The checker considers up to 4,096 ordered pairs and observes only closed native integer functions supported by B's bounded evaluator. Top-level program actions do not run. Foreign library calls are outside this analysis.

Each selected call must meet its precondition and produce a normal return satisfying its runtime postcondition. A false evaluated relation yields `violated` and one concrete witness. An empty selection, an unsupported observation or a selected call without a checked result leaves the requirement `inconclusive` unless another selected pair establishes a violation. A `passed` result covers exactly the selected grid. `--require-proofs` separately enforces B's static proof obligations.

Repeat `--joint` to check several requirements in one invocation. `--json` adds the reports to the normal check response. A failing, inconclusive or malformed requirement makes the command exit nonzero. Existing checks work without a requirement file.

## Choose a law that rules out the mistakes that matter

For an ideal translation, moving the coordinate origin leaves a displacement unchanged. Returning the displacement with its sign reversed satisfies the same relation. A separate directional example distinguishes them. Snapping endpoints to pixel boundaries changes which translations should preserve the result. The right requirement depends on what the function means. [Layout edits, motion models and independent expected outputs](../experiments/joint-design/README.md).
