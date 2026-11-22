# First independently accepted patch

A maintenance change succeeds when the submitted program meets its independent acceptance suite. This pilot tracks the index of that submission. Every run begins with the same code and task text as its paired comparison. The pagination task combines alternating compact widths with two external gutters. The press task combines a quality-control reserve with a rush bonus and a minimum allocation to the slow press. Both preserve a legacy mode, public interfaces, input rejection and an unaffected function.

## Frozen protocol

Two fresh solver contexts per task and feedback provider use up to three candidate submissions. Both providers operate on the same B source and static checker. On the original starter, every solver must run `./inspect` before editing. On each `./submit`, the wrapper copies the program before giving feedback. The final file counts as another attempt if it differs from the last submitted version. An instrument invocation on an unchanged starter is not a candidate submission.

The primary measure is **the first submitted patch that the separate acceptance suite accepts**, with a maximum of three. Stopping after a public pass does not confer acceptance. A run with no independent success is recorded as unresolved, even if the agent stops early. We also record the number of submissions, whether the final file passes, instrument calls and UTF-8 feedback bytes delivered.

The private scorer and instructions were locked before any model saw a task. The frozen B package Git tree was `0aa57e5b9a3f61bec1c281269e19f081cca1fe63`. The SHA-256 of `oracle.py` is `b8285044cec375daa84175e970070046d9796eaa297f2f0532a7cbf510260624`; the common protocol digest is `899c4ee378a70d1ce078b4c0aa82efa0925a1d462e4beaaad11641cc7d1604fe`. The scorer executes every legal input combination for both public endpoints, selected invalid inputs and the unchanged helper. It checks function names, parameter names, parameter types, return types and exactly 51 or 339 behavioral cases. Its formulas are independent of the public properties: it accumulates physical positions in one task and enumerates admissible allocations in the other.

## Compared feedback

The B arm uses the production `check_joint` API and displays its finite-grid JSON, observed calls and failed comparison. The baseline runs independently written, typed Python metamorphic tests against the same lowered B functions. Its failure messages contain both calls, arguments, outputs and the failed numeric assertion. The workspace shows one truthful provider description up front. Identical public examples, input grids, rule names and relations are supplied by both treatments. Pagination uses six relations and presses uses five. The native and Python reports are intentionally delivered in their own formats. The exposure includes the initial diagnostic on the starter, so feedback can affect the first edit.

`properties.py` passes `mypy --strict`. Control runs verify equality of the semantic statuses, number of pairs, failing witnesses and comparison terms for both real providers. This design tests feedback for a B editing task against a strong Python testing alternative. It does not compare writing applications in Python with writing them in B.

Default model settings were shared, with separate fresh contexts and instructional isolation on a shared host. No exact model build, token volume, reasoning time, human response time or monetary cost was available. A report's byte count measures its delivered size only.

## Independent submission results

| Task | Feedback provider | Accepted on submission 1 | First accepted submission for the two replicates | Instrument calls per solver | Total feedback bytes per solver |
| --- | --- | ---: | --- | ---: | ---: |
| Pagination | B joint checker | 2/2 | 1, 1 | 2 | 4,533 |
| Pagination | Typed Python property tests | 2/2 | 1, 1 | 2 | 2,604 |
| Press allocation | B joint checker | 2/2 | 1, 1 | 2 | 3,867 |
| Press allocation | Typed Python property tests | 2/2 | 1, 1 | 2 | 2,317 |

All eight independently executing solver contexts produced a conforming first patch. The four pagination patches each scored 51/51; the four press patches each scored 339/339. Each solver used one initial inspection and one submission. Eight patches were submitted in total, with no retries, premature stops or unsubmitted final edits. Seven unique patches reproduce the eight runs. [Recorded submission histories and artifact names](results.json).

The study reached the minimum possible number of attempts in both arms. B's native reports were larger on both tasks and did not reduce the number of edits. No run needed a repair after its first submission, so this trial cannot estimate the quality of iterative recovery. Neither the number of assertions per candidate nor the number of possible input pairs increases the sample of independent model submissions. The result concerns this same-language comparison with initial feedback; it does not estimate the value of either provider over having no feedback at all.

## Independent checks on the test instruments

For each task a manually supplied correct implementation passed both providers and the full oracle. A deliberately broken joint behavior kept all public examples green but both providers identified the second compact gutter or the missing proof reserve, respectively. Changing a compact row or rush batch size outside the public sample instead passed both providers while failing the independent oracle (49/51 or 330/339). Thus one clean feedback round can still conceal a defective repair.

## Replay

With this B revision installed, run from the repository root:

```sh
trial=experiments/first-pass
work=$(mktemp -d)
cp "$trial/pagination/program.bee" "$work/program.bee"
patch -d "$work" -p1 < "$trial/submissions/pagination-1.patch"
python "$trial/oracle.py" pagination "$work/program.bee"
python "$trial/feedback.py" "$work/program.bee" pagination B
python "$trial/feedback.py" "$work/program.bee" pagination Python
python "$trial/controls.py"
mypy --strict "$trial/properties.py"
```

Select the original task directory and a fresh working copy for each patch named in the run records. Published oracles and patches are suitable for rechecking outcomes; a new blinded trial would require an unseen maintenance task.
