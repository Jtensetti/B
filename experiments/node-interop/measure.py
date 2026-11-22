"""Exercise the supported B interface, a direct Node caller and independent expected values."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
PATH = 'use js:"node:path/posix" as path'
SEMVER = "use js:semver as versions"
EXTRA = "foreign versions.rcompare(Text, Text) -> Int"
WORDS = 'use js:"fastest-levenshtein" as words'
PREFIX = "\n".join((PATH, SEMVER, EXTRA, "foreign versions.inc(Text, Text) -> Option[Text]", WORDS,
                    "foreign words.distance(Text, Text) -> Int", "foreign words.closest(Text, List[Text]) -> Text"))

# Entries name real synchronous exports; nothing in this script implements SemVer or POSIX rules.
CASES = [
    ("path", "join", ["archive/2025", "../2026/item.json"], "archive/2026/item.json"),
    ("path", "join", ["", ""], "."),
    ("path", "join", ["källor", "åäö.txt"], "källor/åäö.txt"),
    ("path", "basename", ["/north/leaf.md"], "leaf.md"),
    ("path", "basename", ["/north/"], "north"),
    ("path", "dirname", ["filename"], "."),
    ("path", "extname", [".env"], ""),
    ("path", "extname", ["archive.tar.gz"], ".gz"),
    ("path", "normalize", ["/a/../b/./c/"], "/b/c/"),
    ("path", "relative", ["/a/b", "/a/c/d"], "../c/d"),
    ("versions", "valid", ["v1.2.3"], "1.2.3"),
    ("versions", "valid", ["1.2.3+build.11"], "1.2.3"),
    ("versions", "valid", ["1.02.3"], None),
    ("versions", "satisfies", ["0.2.10", "^0.2.0"], True),
    ("versions", "satisfies", ["0.3.0", "^0.2.0"], False),
    ("versions", "satisfies", ["1.3.0-beta.2", "^1.2.0"], False),
    ("versions", "satisfies", ["1.3.0-beta.2", ">=1.3.0-beta.1 <1.3.0"], True),
    ("versions", "satisfies", ["1.0.0", ">>"], False),
    ("versions", "compare", ["1.0.0-rc.10", "1.0.0-rc.2"], 1),
    ("versions", "compare", ["1.0.0+build.1", "1.0.0+build.2"], 0),
    ("versions", "compare", ["2.0.0-alpha", "2.0.0"], -1),
    ("versions", "maxSatisfying", [["0.2.9", "0.2.10", "0.3.0"], "^0.2.0"], "0.2.10"),
    ("versions", "maxSatisfying", [["2.0.0", "1.3.0-rc.1"], "^1.0.0"], None),
    ("versions", "rcompare", ["0.2.10", "0.2.9"], -1),
    ("versions", "inc", ["1.0.0-rc.1", "major"], "1.0.0"),
    ("versions", "inc", ["not-a-version", "patch"], None),
    ("words", "closest", ["Trellebog", ["Malmö", "Trelleborg", "Lund"]], "Trelleborg"),
    ("words", "distance", ["lärare", "läraren"], 1),
    ("words", "distance", ["bok", "bok"], 0),
    ("words", "distance", ["😀", ""], 2),
    ("words", "distance", ["é", "e\u0301"], 2),
]


def cli(command, file, *args, cwd):
    return subprocess.run([sys.executable, "-m", "b_lang.cli", command, str(file), *args],
                          cwd=cwd, text=True, capture_output=True, timeout=30)


def checked_output(run):
    if run.returncode:
        raise RuntimeError(f"{run.args} exited {run.returncode}: {run.stdout}{run.stderr}")
    return run.stdout


def program_for_cases():
    lines = [PREFIX]
    for library, name, args, _ in CASES:
        arguments = ", ".join(json.dumps(a, ensure_ascii=False) for a in args)
        expression = f"{library}.{name}({arguments})"
        if name in {"valid", "maxSatisfying", "inc"}:
            expression += ' ?? "<null>"'
        lines.append("print " + expression)
    return "\n".join(lines)


def check_values(cwd, fixture):
    calls = [[library, name, args] for library, name, args, _ in CASES]
    native = subprocess.run(["node", str(ROOT / "native.cjs")], cwd=cwd, input=json.dumps(calls),
                            text=True, capture_output=True, timeout=15)
    report = json.loads(checked_output(native))
    if (report["semver"], report["levenshtein"]) != ("7.8.5", "1.0.16"):
        raise ValueError("Unexpected package versions. Install the locked npm dependencies.")
    fixture.write_text(program_for_cases())
    lines = checked_output(cli("run", fixture, "--strict", cwd=cwd)).splitlines()
    for case, node, emitted in zip(CASES, report["values"], lines, strict=True):
        expected = case[-1]
        if type(node) != type(expected) or node != expected or emitted != ("<null>" if expected is None else str(expected)):
            raise AssertionError((case, node, emitted))
    return {"node": report["node"], "semver": report["semver"], "levenshtein": report["levenshtein"],
            "matched_value_cases": len(CASES)}


def boundaries(cwd, fixture):
    # A declaration is an assumption about the interface. Each unsafe program
    # must be rejected at the appropriate stage before it prints a successful result.
    bad = {
        "undeclared_export": ("check", "E_FOREIGN", SEMVER + '\nprint versions.rcompare("0.2.10", "0.2.9")'),
        "bad_curated_argument": ("check", "E_TYPE", SEMVER + '\nprint versions.satisfies(12, "^1")'),
        "lying_result_type": ("run", "declared Text", SEMVER + '\nforeign versions.rcompare(Text, Text) -> Text\nprint versions.rcompare("1.0.0", "2.0.0")'),
        "missing_export": ("run", "Missing named export", SEMVER + '\nforeign versions.absentReleaseMethod(Text) -> Text\nprint versions.absentReleaseMethod("1.0.0")'),
        "exception_inside_npm": ("run", "Invalid Version", SEMVER + '\nprint versions.compare("banana", "1.0.0")'),
        "unsafe_int": ("run", "safe integer range", SEMVER + '\nforeign versions.cmp(Int, Text, Int) -> Bool\nprint versions.cmp(9007199254740992, "===", 9007199254740993)'),
    }
    rejected = {}
    for key, (stage, diagnostic, source) in bad.items():
        fixture.write_text(source + "\n")
        if stage == "run":
            checked_output(cli("check", fixture, "--strict", cwd=cwd))
        failed = cli(stage, fixture, "--strict", cwd=cwd)
        if not failed.returncode or diagnostic not in failed.stderr:
            raise AssertionError(f"Expected {key} to be rejected by {stage} for {diagnostic}: {failed.stderr}")
        rejected[key] = stage

    rounded = subprocess.run(["node", str(ROOT / "native.cjs")], cwd=cwd,
                             input='[["versions","cmp",[9007199254740992,"===",9007199254740993]]]',
                             text=True, capture_output=True, timeout=15)
    if json.loads(checked_output(rounded))["values"] != [True]:
        raise AssertionError("Native numeric control did not alias the two integers")
    return rejected


def measure():
    with tempfile.TemporaryDirectory(dir=ROOT) as local, tempfile.TemporaryDirectory() as empty:
        # The B file lives under its npm project. cwd deliberately has no node_modules.
        fixture = Path(local) / "calls.bee"
        data = check_values(empty, fixture)
        if checked_output(cli("run", ROOT / "release.bee", "--strict", cwd=empty)).strip() != "dist/0.2.10":
            raise AssertionError("Wrong release chosen")
        if checked_output(cli("run", ROOT / "explicit.bee", "--strict", cwd=empty)).strip() != "-1":
            raise AssertionError("Wrong descending release order")
        if checked_output(cli("run", ROOT / "spelling.bee", "--strict", cwd=empty)).splitlines() != ["Trelleborg", "1"]:
            raise AssertionError("Wrong correction from the package with no built-in B signatures")
        data.update(spelling_output=["Trelleborg", 1], release_output="dist/0.2.10", explicit_output=-1,
                    rejections=boundaries(empty, fixture))
        return data


if __name__ == "__main__":
    print(json.dumps(measure(), indent=2))
