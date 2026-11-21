# B source filenames

## Decision: `.bsrc`

The recommended B source filename suffix is **`.bsrc`** (B source), starting with B v0.2. The CLI accepts `.bsrc` and legacy `.b` files. New examples, editor configuration and documentation use `.bsrc`.

## Why not `.b`?

`.b` is already used by **Ken Thompson's original B language**, created at Bell Labs in 1969 as a precursor to C, and by tools compiling source for that language. It also appears as an extension for **Brainfuck** and **Limbo**, among other software/data formats. B's v0.1 used `.b` without assessing these conflicts.

- Historical B: https://en.wikipedia.org/wiki/B_(programming_language)
- Current old-B compiler using `.b`: https://github.com/Spydr06/BCause
- Languages and formats claiming `.b`: https://blog.mathieuacher.com/PL-ultimate-llm/ext/b/index.html

There is **no global filename extension registry** ensuring a suffix is uniquely available. We did not find a clearly established competing programming-language use of `.bsrc` in a targeted web search in November 2026. This is not an exclusive reservation. Additional local/filetype associations may exist.

## Compatibility contract

- New source files: `program.bsrc`.
- Legacy source files: `program.b` continue to be accepted.
- Unrelated suffixes are rejected by the CLI with `E_EXTENSION`.
- Source file content and language semantics are identical for `.bsrc` and `.b`.
- GitHub may not recognize `.bsrc` as a language until GitHub Linguist supports it. The included VS Code grammar recognizes `.bsrc` without stealing existing `.b` associations.
- `b` remains the command-line tool name in this experimental project; it may conflict with another command installed on a user's machine. `python -m b_lang.cli` is an alternative.
