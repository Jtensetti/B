# Lecture subtitle timing checker

Check an exported lecture for timing issues. B and typed Python supply interchangeable decision functions. A shared Python host reads cues, counts words, tracks previous end times and reports one issue per cue. The included lecture is synthetic.

```sh
python experiments/subtitle-maintenance/check.py experiments/subtitle-maintenance/lecture.vtt --engine b
python experiments/subtitle-maintenance/check.py experiments/subtitle-maintenance/lecture.vtt --engine python
python experiments/subtitle-maintenance/replay.py
```

The output columns are the timing line number, cue identifier (or a dash), and issue. Exit 0 means clean, 1 means findings, and 2 means invalid input or a usage error. Both engines report four cues in the supplied file. A 1 ms spoken cue contained in earlier speech is reported as `overlap` under release 2. Its start was 300 ms before the earlier speech ended.

## Timing policy

`--revision` selects 0, 1 or 2 (default). The baseline requires every cue to last at least one second and flags any overlap. Release 1 admits spoken cues with one or two words at 550 ms and sound effects at 750 ms. Other spoken cues, including empty ones, retain a 1,000 ms floor.

Release 2 lets a spoken cue **start** up to 80 ms before preceding speech ends. Any positive overlap involving a sound effect is flagged. Each boundary is inclusive. A start exactly at another cue's end is allowed. A reversed or zero duration takes priority over overlap, which takes priority over a short duration. Only positive-duration cues update the running maximum end times, maintained separately for speech and sound. These thresholds are the fictional editor's product choices.

The reader accepts UTF-8 WebVTT files with a header, blank-separated cues, optional cue identifiers, multiline payloads, cue settings after the ending timestamp, and non-decreasing starts. It ignores NOTE, STYLE and REGION blocks. It treats a payload entirely in square brackets as a sound effect after removing markup and resolving HTML entities. It counts hyphenated words and contractions as single words. Files using additional header metadata or malformed timing lines can be rejected. The reader is a small shared lecture-export profile rather than a general WebVTT validator. All parsing, file I/O and state tracking are Python even when B supplies the decision function.

## Maintenance trial

One fresh solver context per language maintained its own code across two successive requests. Both received equivalent starter policies, the same product requirements and public examples, no hidden examples, and a two-submission limit per request. They sent full function source and received public feedback. B used strict compilation; the Python candidates passed mypy strict checks. The [original requests and public cases](protocol.py) and [independent boundary grid](oracle.py) were frozen before assignment. Their SHA-256 digests were respectively `7109175a9c196a934157d1184db3311b9248e19a3307492236f5acd0b07ff7ad` and `a2486859dceafb5b16568158da89793d67730ad1a1d4afddbebd42223a7d3257`.

| Submitted change | B, frozen oracle | Python, frozen oracle | Whole-source tokens, B / Python |
| --- | ---: | ---: | ---: |
| Duration floors, first submission | 6,144/6,144 | 6,144/6,144 | 96 / 112 |
| Overlap tolerance, first submission | 6,120/6,144 | 6,120/6,144 | 120 / 139 |
| Same change after a clarification | 6,144/6,144 | 6,144/6,144 | 108 / 133 |

Both initial overlap revisions passed all three public examples. The frozen checker expected `overlap` if earlier speech continues for 81 ms after a new spoken cue starts, even when the new cue lasts only 1 ms. Both solvers returned `brief`: the two cues share only 1 ms of playback. The request said “up to and including 80 ms of overlap.” It left those two interpretations open. All 24 misses involved this distinction.

The original [B](first-submit/rev2.bee) and [Python](first-submit/rev2.py) submissions are retained. A separately identified **post-trial** reading based on the length of the shared time interval accepts all 6,144 outputs of each initial revision. We then told both maintainers to compare the new start to the earlier end even in the 1 ms case. Each returned the released code on its next submission and satisfied the original oracle. No initial scores were replaced.

Each engine solved one of two requested changes on its first submission under the frozen rubric. B consumed 324 and Python 384 tokens of submitted source over the three submissions, using `o200k_base` with one final newline per file. Both rewrote the complete function each time. Prompt, reasoning, elapsed model time and total session costs were unmeasured. The shared host setup and authoring the function interfaces are excluded. One sequence, one solver per language and several thousand related boundary checks give no estimate of success rates on unrelated projects. A single pre-edit question about the 1 ms cue would have established which behavior the editor wanted.

## A question for the editor

After the trial we supplied the two candidate meanings to B's existing clarification command. For this measurement the cue is speech, has positive duration and overlaps earlier speech only. The tool selects an input from twelve possible pairs of duration and lead time. It asks whether it is acceptable to omit an overlap warning when a one-millisecond cue starts 81 ms before the previous speech ends. Either answer distinguishes the two proposed policies, and the replay checks both.

```sh
b clarify experiments/subtitle-maintenance/overlap.bee experiments/subtitle-maintenance/overlap.json
```

The candidates were supplied after seeing the disagreement. This demonstrates finding a useful question once the alternatives are known. Discovering the ambiguity from the original brief, and determining when asking saves a repair, remain open.

## Runtime on the sample file

On one Linux host with Python 3.12.14, launching a fresh process for the eight-cue lecture took a median of 151.366 ms with B and 35.337 ms with Python. With each policy loaded once, rereading, parsing and checking the whole file took 0.110 ms and 0.053 ms respectively. Each engine produced the same output. The [timing harness](timing.py) alternates run order over 11 measured rounds after one discarded warmup. Cold B timing includes loading the B compiler and compiling the source. These machine-specific measurements exclude model time and billing.

```sh
python experiments/subtitle-maintenance/timing.py
```
