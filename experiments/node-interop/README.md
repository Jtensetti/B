# Calling two npm packages from B

The release selector combines Node's POSIX path library with npm's `semver` 7.8.5. Given stable versions 0.2.9 and 0.2.10, an incompatible 0.3.0 and a prerelease 0.2.11-rc.1, it selects `dist/0.2.10`. B knows the signatures of the two exports used by this program. [Release selector](release.bee) · [Node POSIX path reference](https://nodejs.org/api/path.html#pathposix) · [node-semver](https://github.com/npm/node-semver).

A second program uses `fastest-levenshtein` 1.0.16 to suggest a spelling and report the edit distance. B has no catalog entries for this package. Two `foreign` declarations describe the named exports. For “Trellebog”, the program returns “Trelleborg” and distance 1. Both packages run in Node. [Spelling example](spelling.bee) · [fastest-levenshtein](https://github.com/ka-weihe/fastest-levenshtein).

With B installed and Node 20+ available, run from the repository root:

```sh
npm ci --prefix experiments/node-interop --ignore-scripts --no-audit --no-fund
b run examples/node-path.bee --strict
b run experiments/node-interop/release.bee --strict
b run experiments/node-interop/spelling.bee --strict
python experiments/node-interop/measure.py
```

The [channel filter](channel.bee) uses three runtimes in one program. Python decodes an artifact path, .NET checks its channel structure, and Node checks the file name and release range. Running this additional example requires the .NET 10 SDK.

## How much has to be specified?

| Ready-to-run task | Distinct JS exports | B declarations written by the caller | Observed output |
| --- | ---: | ---: | --- |
| Normalize the path to a translated document | 2 | 0 | `translations/en/messages.json` |
| Choose the latest compatible stable release and its directory | 2 | 0 | `dist/0.2.10` |
| Compare two releases in descending order | 1 | 1 | `-1` |
| Correct a place name and calculate its distance | 2 | 2 | `Trelleborg`, `1` |

For the descending comparison the experiment also removes the declaration. The first static check identifies the unregistered export. Adding `foreign versions.rcompare(Text, Text) -> Int` allows the same expression to run. This is one deliberately induced repair. The table measures the interface work in supplied solutions. It cannot tell how many drafts an AI or person would need when writing them from scratch.

## Value and failure checks

The harness submits 31 calls through B and separately to a native Node program. Both outputs must match independent expected values. The cases cover POSIX path rules, version ranges, prereleases, build metadata, nullable returns, lists, reversed comparison and spelling. The B program runs from an unrelated working directory with no local npm dependencies, resolving the installed packages relative to the B source. Locally the 31 cases passed with Node 24.22.3 and both versions pinned in the lockfile.

Six rejection controls distinguish an absent declaration or a statically wrong argument from a call that passes type checking and fails at the Node boundary. The latter group includes a false return declaration, an absent named export, a real exception in npm and an out-of-range integer. Native JavaScript gives the same numeric value to 9007199254740992 and 9007199254740993. B rejects the call carrying these integers.

A correctly computed result can still answer the wrong product question. The spelling library returns 2 when deleting 😀, and 2 when comparing the precomposed “é” with “e” followed by a combining acute accent. These cases match the native library's UTF-16 code-unit behavior. A requirement expressed in visible characters would need a different distance or preprocessing. Annotations can describe `(Text, Text) -> Int` without resolving that choice.

B's Node adapter supports synchronous named exports with supported value types. In this experiment, the hand-maintained `semver` catalog covers four selected methods. Input and output guards check boundary types at execution. Behavioral guarantees about third-party code still require independent evidence.
