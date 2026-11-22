# A device-timing profile in B

A recorder produces the signed difference in microseconds between the observed and scheduled time of each tick. The requested report gives the sample count, total signed offset, count of early ticks, earliest offset and latest offset. Empty recordings return zero in each field. Early and late offsets may cancel. Dividing total offset by count gives the mean for a nonempty recording. Every implementation returns the same dictionary with exact integer values.

[profile.bee](profile.bee) is the whole B implementation. [The Python alternatives](python_baselines.py) use either built-ins with a generator for the conditional count, or one explicit pass.

## Independent checks

The fixed capture in [pulse_cases.py](pulse_cases.py) was collected on a host timer. We scheduled 32 absolute deadlines 2 ms apart using Python’s monotonic nanosecond clock, slept until each deadline, then recorded the measured offset rounded down to microseconds. Its expected report is `{"n":32,"net":2604,"early":0,"lo":70,"hi":118}`. The run contains only late ticks, so the measured minimum of 70 also checks that the empty-list default of zero did not enter the reduction.

Ten more fixed cases cover empty and all-zero streams, extremes, cancellation, and sums larger than 64 bits. An independent frequency calculation supplies the answers for all lists of length 0 through 5 over the alphabet `{-3,0,6}`. For every list and every cut, the runner also profiles both halves and merges them. Counts and totals add. Low and high use the extrema of **nonempty** halves, which the `n` field identifies. This tests the hypothesis that those five reported quantities suffice to profile concatenated recordings without retaining the source sequence. B currently computes the complete profile sequentially. The merge is an experimental oracle.

The fixed recordings `[6,-3,6,-3]` and `[-3,-3,6,6]` have identical reports. Only the second contains two consecutive late ticks. A requirement about consecutive misses needs additional state specifying order.

An [executable follow-up](order_check.py) keeps three Boolean facts for each nonempty chunk: whether its first tick is late, its last tick is late, and it already contains a consecutive late pair. Empty chunks are represented separately. Joining adjacent chunks can create a new pair only at their shared boundary. Across all 511 late/on-time patterns of lengths zero through eight, the result matched direct inspection at 4,097 two-part splits and 18,943 three-part splits under both parenthesizations. Order matters, yet the original sequence can be discarded after these facts are computed. This follow-up runs in Python and supplies a reference for a future B operation.

## Running the experiment

Run these commands from the repository root with B installed in editable mode.

```sh
python experiments/collection-reductions/measure.py
python experiments/collection-reductions/measure.py --timing
python experiments/collection-reductions/order_check.py
```

`measure.py` first compares every implementation against the independent cases. It checks invalid data at the three checked entry points, including a boolean mixed with integers. Timings measure the same result on prebuilt valid lists. Warm samples rotate the engine order and report the median of seven batches. The 10,000-element workload uses a fixed seed and uniform synthetic integer offsets from −250 to +250 µs. Data generation and I/O are outside the timed call.

- **B public** is the strict-compiled B function called normally from Python, with its input and result validation and snapshots.
- **Python checked** uses an exact-list/exact-int check, a shallow snapshot appropriate for integer elements and the built-in reducers.
- **Python with B guards** runs the built-in reducers with the same input and output guards as B. This helps identify boundary overhead.
- **B kernel** calls the generated single-pass reduction helper directly. Timing includes construction of the output dictionary and assumes an already checked input list.
- **Python built-ins** and **Python loop** assume the input list is already valid. Both include the output dictionary allocation.

The cold measurement starts a fresh Python child process for each checked implementation and processes the same recorded trace. B reads and compiles its source in that process. Python loads its source module through the ordinary import system, potentially using cached bytecode. Both include interpreter and driver startup, JSON encoding and process exit. No subprocess startup time is subtracted.

## Observed results

On CPython 3.12.14 and 3.13.5, all six measured call paths passed all 375 reference cases. Merging the results of the B function on two parts passed all 2,079 cuts. The three checked entry points rejected each of the four invalid inputs.

Warm median microseconds per call on the same host follow below.

| Interpreter | Input length | B public | Python checked | Python with B guards | B kernel | Python built-ins | Python loop |
|---|---:|---:|---:|---:|---:|---:|---:|
| 3.12.14 | 0 | 7.00 | 0.76 | 7.58 | 0.18 | 0.64 | 0.14 |
| 3.12.14 | 32 | 9.02 | 2.59 | 9.53 | 1.50 | 2.04 | 1.68 |
| 3.12.14 | 10,000 | 802 | 878 | 868 | 588 | 618 | 623 |
| 3.13.5 | 0 | 5.70 | 0.49 | 5.88 | 0.16 | 0.40 | 0.13 |
| 3.13.5 | 32 | 8.71 | 2.34 | 8.41 | 2.21 | 1.61 | 2.13 |
| 3.13.5 | 10,000 | 1,029 | 852 | 891 | 760 | 593 | 711 |

Cold runs processed the 32-tick capture. Times are median milliseconds.

| Interpreter | B public | Python checked |
|---|---:|---:|
| 3.12.14 | 210.0 | 39.2 |
| 3.13.5 | 206.8 | 32.7 |

The profile expresses five quantities with one B expression. The backend takes the unfiltered count from the list length once before its loop. On the real 32-tick capture the generated and hand-written loops ran within 0.19 µs of each other. With 10,000 mixed values the B kernel ran fastest in the 3.12 run, while the Python built-ins finished first in the 3.13 run despite traversing the list several times. The ranking of the checked public calls also reversed between interpreters. The additional public boundary work was particularly visible on the shorter lists. These are samples from one host and one reduction, with no estimate of hardware-to-hardware or process-to-process variance. This experiment measured execution and exact results. A separate [first-use task](first-use/README.md) exercises the syntax with a fresh model-written program in each language.


## How much source does it take?

Counting the complete profile declaration, including its final newline, gives 61 tokens for B with the o200k_base encoding. The Python built-in solution takes 57 and the explicit Python loop takes 128, as written in [the timed source](python_baselines.py). Those Python functions have no annotations. Giving both the same name and an annotated declaration (`def profile(xs: list[int]) -> dict[str, int]:`) brings them to 65 and 136 tokens respectively. Annotations alone add no runtime checking in Python. These numbers describe one source representation and one tokenizer.

## Cost of the input check

B validates each element and snapshots a list passed to a typed function. The previous implementation redispatched on the full type descriptor for every integer. For lists of exact integers, booleans and strings, the new implementation selects the scalar type once, checks each item's exact runtime type and returns a shallow copy. An incorrect element still identifies the first type mismatch. A public call therefore includes work proportional to the input length even for a report containing only an unfiltered count.

For `guard(list_of_ints, "List[Int]")` with the input list constructed in advance from `range(100000)`, median guard time fell from 85.75 to 1.50 ms on CPython 3.12.14 and from 71.45 to 1.65 ms on 3.13.5. Both revisions ran in the same process with a warm descriptor cache, alternating order across nine batches of three calls. This measures only the input boundary. The profile timings above include the computation and the output boundary.
