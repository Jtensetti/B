# The journey trial: from an empty file through four changes

This experiment measures the long-term goal in [the vision](../../docs/vision.md). Can a model, starting from an empty directory, build a real program with libraries from two ecosystems in B, and carry it through changes, with fewer wrong results and less total work than in typed Python?

## Design

- **Task.** A command-line dependency resolver ([steps](steps/)). It reads a JSON manifest and chooses the highest available version allowed by npm's semver rules. In later steps it suggests spellings for unknown packages (edit distance), honors pins, never picks prereleases through a range, and reports a summary. The specification names the npm `semver` package's semantics, as real tooling around npm must.
- **Libraries.** The B program can use Python's standard library and the npm packages `semver` and `fastest-levenshtein`, which are installed in each workspace. The Python program can use the standard library, and may call the same npm packages through `node` if it chooses.
- **Solvers.** Four instances of the same model (Claude Sonnet, through Claude Code subagents), two per language, each in its own empty workspace. B solvers learn B from its documentation during the trial, which is part of B's cost. Steps arrive one at a time in the same conversation. A solver may ask one question per step.
- **Hidden tests.** 20 fixtures, graded after each step against an oracle that uses the npm libraries the specification names. Inputs for steps 1–2 carry no pins. Solvers never see hidden results. They test with their own inputs.
- **Work.** For each step: the solver's tokens, tool calls and wall time as reported by the agent runtime.

The specification grew to eight steps during the trial: dist-tags (6), outdated packages (7) and loosely written versions (8) were added. Every solver received them in the same order, and none had seen them in advance. Steps 1–5 are graded on the original 20 fixtures, and steps 6–8 on all 27.

## Results

**Correctness.** Every solver passed every hidden fixture at every step: 4 solvers × 8 steps, with no failures ([grades](results/grades.txt)). Typed Python and B produced the same number of wrong results, zero. For errors, this task did not separate the languages.

**Work** ([per step](results/work.json), measured from the agent transcripts by [work.py](results/work.py)):

| Solver | Output tokens: build (step 1) | Output tokens: 7 changes | Output tokens: total | Tool calls | Seconds | Final program |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B 1 | 5,186 | 18,072 | 23,258 | 28 | 130 | 48 lines |
| B 2 | 3,519 | 17,391 | 20,910 | 23 | 122 | 33 lines |
| Python 1 | 31,309 | 9,914 | 41,223 | 20 | 164 | 530 lines |
| Python 2 | 28,404 | 10,001 | 38,405 | 29 | 342 | 472 lines |

Input tokens, which are mostly re-read context, were 4.6 M and 3.5 M for B against 3.3 M and 4.3 M for Python. They did not separate the languages either.

**What this means.**

- **B wins the build by borrowing.** Both Python solvers rewrote npm's semver range logic from scratch, about 450 lines. They tested it against `node` with 3,000–4,000 random cases. The B solvers called the npm library directly. Including learning B from its documentation, B's build took 3,500–5,200 output tokens against 28,000–31,000.
- **B loses the changes.** Over the seven changes, the B solvers spent about 1.8 times as many output tokens as the Python solvers. The B programs show why:
  - Functions cannot have local bindings, so the logic lives in long one-line expressions that are rewritten rather than edited.
  - `Option` values are not narrowed after a `!= none` test, which leads to repeated `?? ""`.
  - B's semver catalog lacked `prerelease` and `clean`. The solvers fell back on regular expressions and on building `1.0.0 || 2.0.0-beta.1` ranges.
  - There is no maximum by a comparator, so one solver wrote a quadratic search.
- **Total work favors B on this task**, about 0.55 times the output tokens and 0.5 times the wall time. That comes entirely from the build. A longer life with more changes would erode it.

**Against the long-term goal**, the trial shows a model starting from an empty file and building a working program with libraries from two ecosystems. It also shows the model carrying the program through seven changes with less total work than typed Python. It does **not** show fewer errors: both reached the ceiling. With two solvers per language and one task, the work difference is evidence, not proof.

## Limits

- One task, chosen by the author of B. It favors borrowing, because its semantics are defined by an npm library. A task whose logic lives in the program rather than in a library would weigh the change costs more heavily.
- The Python solvers could call `node`. Both used it only as a test oracle and shipped pure Python.
- The solvers were told not to read the hidden fixtures, which lived outside the repository during the trial, but this was not enforced.
- Output tokens count what the model wrote, including reasoning. Input tokens are dominated by cached context. Neither is a price.

## Reproduce

```sh
node experiments/journey/oracle.mjs                      # recompute expected outputs
python experiments/journey/grade.py 8 path/to/workspace -v
```

The solvers' final programs are in [solutions](solutions/). Each workspace needs `node_modules` from [node-interop](../node-interop/).
