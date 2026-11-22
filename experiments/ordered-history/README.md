# Counting events that depend on the past

The four [counting expressions](patterns.bee) answer two questions about ordered data. Given signed pulse offsets, how many ticks were late immediately after another late tick? Given nonempty half-open subtitle intervals, how many cues overlap at least one earlier cue in the supplied sequence? Each position contributes at most one, including when several earlier cues qualify.

| B function | Input contract for this task | History selected by B |
| --- | --- | --- |
| `late_pairs` | Positive offsets are late, zero is on time | The previous tick's Boolean test |
| `overlaps_sorted` | Complete start/end records, positive duration, nondecreasing start times | Greatest preceding end time |
| `overlaps_neighbors` | Same domain; checks only the preceding cue | Previous cue |
| `overlaps_any_order` | Complete start/end records, positive duration, any input order | Search earlier cues until the first witness |

The compiler obtains the running maximum from the comparison of a previous end against the current start. The sorted-input contract comes from the application. On `[(10,11),(0,1)]` the single inequality returns 1 even though the intervals are disjoint. The two-sided test returns 0. A B dictionary has optional keys; the examples use a fallback of zero and require the caller to supply both endpoints. Missing keys and reversed durations need their own application policy.

For the sorted nested intervals `[(0,100),(10,20),(30,40)]`, both short intervals overlap the first one. The immediate-neighbor check returns 1. Remembering the greatest earlier end returns 2. Touching endpoints count as disjoint under the strict inequality. Three consecutive late ticks contribute two adjacent pairs.

The public example `overlap_count(cues) -> Option[Int]` checks each input for both integer endpoints and positive duration. It returns `none` for missing endpoints and nonpositive durations. It checks consecutive start times to choose the fast sorted rule or the general two-sided rule. Thus both sorted and unsorted valid input yield a concrete count. The timings below isolate the counting functions. They exclude this wrapper’s validation and dispatch.

## Independent checks

[check.py](check.py) scores the B implementations against two independent definitions. A run of `r` consecutive late ticks contains `r-1` adjacent pairs. Two half-open intervals intersect when their intersection has positive width. The same scorer also checks the Python implementations used in the timing study.

- All 511 binary pulse words up to length eight, plus a list with negative offsets and an integer exceeding 64 bits.
- All 1,555 sequences of up to four intervals whose distinct integer endpoints lie between 0 and 3. These include duplicate cues and tied starts. The sorted-input implementation and the neighbor check were additionally scored on the 423 sequences with nondecreasing starts.
- The existing [lecture subtitle fixture](../subtitle-maintenance/lecture.vtt) contains eight cues. Its reader enforces ordered starts. One reversed cue was excluded and reported separately. Among the seven valid cues, three positions overlapped earlier speech or sound under the strict geometric rule used here. The product's speech grace period is a separate policy.

The [Boolean loop proof](loop-proof.md) covers all finite input lengths for one particular emitted helper.

From the repository root with B installed:

```sh
python experiments/ordered-history/check.py
python experiments/ordered-history/validate_boolean_loop.py
python experiments/ordered-history/timing.py
b ir experiments/ordered-history/patterns.bee --strict
```

## Warm execution

The [timer](timing.py) compiles B once, constructs inputs in advance and reports median microseconds per call over seven rotated batches after warm-up. It compares public B functions with [Python implementations](python_patterns.py) on identical valid inputs. Columns marked “with guards” include B's same input snapshot, type validation, and scalar result check. The standalone input guard column isolates the input-boundary work. Raw Python accepts prevalidated inputs. Sub-microbenchmarks can vary between runs.

The pulse sample contains 4,096 seeded integer offsets. The sorted sample has 1,024 cues with varied durations. The arbitrary-order sample consists of 512 disjoint intervals presented in reverse order. Every prefix search in that sample must exhaust its earlier candidates. As a stronger baseline, the indexed Python implementation uses a binary indexed tree holding the greatest observed end for each range of start coordinates. A prefix query handles all earlier intervals with starts below the current end. Building and querying that index takes O(n log n) time across the sequence.

| CPython | Task | Public B (µs) | Python algorithm | Raw Python (µs) | Python with guards (µs) | Input guard alone (µs) |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| 3.12.14 | 4,096 pulses | 149.2 | previous Boolean | 85.2 | 152.6 | 58.6 |
| 3.12.14 | 1,024 sorted cues | 2,897.2 | running maximum | 57.0 | 2,902.3 | 2,851.9 |
| 3.12.14 | 512 unordered cues | 9,453.4 | prefix search | 3,836.9 | 5,007.0 | 1,488.5 |
| 3.12.14 | same input | 9,453.4 | indexed query | 467.1 | 1,959.0 | 1,488.5 |
| 3.13.5 | 4,096 pulses | 181.4 | previous Boolean | 115.9 | 189.0 | 65.6 |
| 3.13.5 | 1,024 sorted cues | 2,339.1 | running maximum | 77.5 | 2,329.0 | 2,260.7 |
| 3.13.5 | 512 unordered cues | 9,864.1 | prefix search | 4,883.4 | 5,575.6 | 1,130.3 |
| 3.13.5 | same input | 9,864.1 | indexed query | 499.5 | 1,625.3 | 1,130.3 |

The two specialized B plans ran close to the corresponding Python loops with matching checks on this host. On the sorted cue task the check and recursive snapshot of the dictionary input dominated both implementations. For 512 unordered disjoint cues, B's general fallback evaluated up to 130,816 prior/current pairs. The indexed Python algorithm with equivalent guards ran about 4.8 to 6.1 times faster. Distinguishing when both endpoints require an index is a concrete compiler optimization to test. The results cover two input domains on one machine; speed and adequacy of the specified rule remain separate questions.
