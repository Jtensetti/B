# B source file extension

**Decision (v0.3): `.bee` is the preferred extension.** Existing `.bsrc` (v0.2) and `.b` (v0.1) continue to work. `b` refuses `.be` by default to avoid an established conflict.

| Candidate | Existing use | Decision |
| --- | --- | --- |
| `.b` | Historic Bell Labs B language and other uses | Legacy B compatibility only |
| `.be` | Berry programming language, documented executable script suffix | Do not claim |
| `.bee` | BeeSchema schema files, older Bee Archiver data files | Adopt for B, despite non-exclusive use |
| `.bsrc` | B v0.2 source convention | Keep compatible |

A file suffix is not a global namespace or a proof of uniqueness. `.bee` must never be identified as B based on suffix alone where content could originate from other software. The VS Code grammar uses an extension association only when explicitly installed, and the B CLI validates the source using its own parser.

Primary sources and examples:
- Berry documents `.be`: https://berry.readthedocs.io/en/latest/source/en/Chapter-1.html
- BeeSchema uses `*.bee`: https://github.com/Michael-K-GH/BeeSchema
- Bee Archiver `.bee`: https://file.org/extension/bee

No binary file format or MIME registration is claimed by B v0.3.
