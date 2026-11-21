# B source suffixes

**Decision: `.bee` is the canonical suffix.** `.b4` is a fun, optional alternate spelling; `.bsrc` and `.b` are accepted for backward compatibility. Neither name nor suffix is globally exclusive.

| Suffix | Known collision | B policy |
| --- | --- | --- |
| `.b` | Original Bell Labs B language, among others | Legacy compatibility only |
| `.be` | Berry language | Not used |
| `.bi` | FreeBASIC include/header files | Not used |
| `.b4` | Older Helix Nuts and Bolts data files; similar B4X ecosystem names (.b4a/.b4i/.b4j) | Accepted alias, not canonical |
| `.bee` | BeeSchema and older Bee Archiver use | Preferred for this project |
| `.🐝` | Unicode filenames can work, but build tools and cross-platform handling vary | Joke, not registered/accepted |

An extension is not a content-type guarantee. The CLI reads UTF-8, checks the actual grammar, and emits `E_EXTENSION` for other suffixes. No MIME registration or exclusive ownership is claimed.

References:
- https://www.freebasic.net/wiki/KeyPginclude
- https://gaijin.at/en/infos/filename-extensions/letter-b
- https://www.b4x.com/guides/B4XGettingStarted.html
- https://berry.readthedocs.io/en/latest/source/en/Chapter-1.html
- https://github.com/Michael-K-GH/BeeSchema
