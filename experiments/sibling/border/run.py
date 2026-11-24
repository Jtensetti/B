"""Run fixed provider mutations against archived final programs. See PREREGISTRATION.md."""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIBLING = HERE.parent
sys.path.insert(0, str(SIBLING))
from checks import CHECK, check

SEEDS = json.loads((HERE / "seeds.json").read_text())
B_COMMIT = "01a91593241803567c35534acbe3e041d4936b11"


def tool_versions():
    commands = {"python": [sys.executable, "--version"], "mypy": ["mypy", "--version"],
                "node": ["node", "--version"], "typescript": ["tsc", "--version"],
                "go": ["go", "version"], "rust": ["rustc", "-V"], "cargo": ["cargo", "-V"],
                "dotnet": ["dotnet", "--list-sdks"]}
    versions = {}
    for name, cmd in commands.items():
        try:
            versions[name] = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            versions[name] = str(exc)
    return versions


def workspace(task, solver, modules, ws):
    shutil.copytree(task / "solutions" / solver, ws)
    libs = ws / "libs"
    # B's archive omits the supplied libraries. Fill missing files only.
    for src in (task / "libs").rglob("*"):
        dest = libs / src.relative_to(task / "libs")
        if src.is_file() and not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
    (ws / "node_modules").symlink_to(modules, target_is_directory=True)


def apply_seed(ws, seed):
    path = ws / "libs" / seed["file"]
    source = path.read_text()
    if source.count(seed["before"]) != 1:
        raise ValueError(f"Expected one anchor in {seed['file']}")
    path.write_text(source.replace(seed["before"], seed["after"], 1))


def check_variant(task, solver, modules, seeds, variant):
    with tempfile.TemporaryDirectory(prefix=f"sibling-{solver}-") as work:
        ws = Path(work) / solver
        workspace(task, solver, modules, ws)
        if variant == "comment":
            for file in sorted({s["file"] for s in seeds}):
                marker = "#" if file.endswith(".py") else "//"
                with (ws / "libs" / file).open("a") as dest:
                    dest.write(f"\n{marker} Library maintenance.\n")
        elif isinstance(variant, dict):
            apply_seed(ws, variant)
        return check(solver[:-1], ws)


def classify(check_result, symbol):
    if check_result["exit"] == 0:
        return "miss"
    if check_result["exit"] is None:
        return "unresolved"
    diagnostic = check_result["diagnostic"]
    # Only explicit call-site/type diagnostics naming the changed API get automatic credit.
    # Preserve all other rejections for review.
    if (re.search(rf"\b{re.escape(symbol)}\b", diagnostic, re.I)
            and re.search(r"E_(?:TYPE|ARITY|FOREIGN)|arguments?|parameters?|CS7036|E0061", diagnostic, re.I)
            and not re.search(r"timed out|could not (?:build|download)|NU1301|fatal error:", diagnostic, re.I)):
        return "catch"
    return "unresolved"


def measure(task, solver, modules):
    seeds = SEEDS[task.name]
    row = {"task": task.name, "solver": solver,
           "outcomes": {s["kind"]: "unresolved" for s in seeds}, "checks": {}}
    scores = task / "results" / "results.json"
    if not scores.exists() or not (task / "solutions" / solver).is_dir():
        return {**row, "reason": "Final submission or step-5 score missing"}
    published = json.loads(scores.read_text()).get(solver, {}).get("steps", {}).get("5")
    row["step5"] = published
    for control in ("clean", "comment"):
        row["checks"][control] = check_variant(task, solver, modules, seeds, control)
    if (not published or published["wrong"] != 0 or published["of"] <= 0
            or any(c["exit"] != 0 for c in row["checks"].values())):
        return {**row, "reason": "Control ineligible"}
    for seed in seeds:
        kind = seed["kind"]
        try:
            result = check_variant(task, solver, modules, seeds, seed)
        except ValueError as exc:
            row["checks"][kind] = {"exit": None, "diagnostic": str(exc)}
            continue
        row["checks"][kind] = result
        row["outcomes"][kind] = classify(result, seed["symbol"])
    return row


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("task", choices=SEEDS)
    p.add_argument("language", choices=CHECK)
    p.add_argument("node_modules", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    modules = args.node_modules.resolve()
    for package in ("fastest-levenshtein", "semver", "@types/node"):
        if not (modules / package / "package.json").is_file():
            p.error(f"Missing {package} in {modules}")
    # Editable install of the registered compiler is required, also for b check subprocesses.
    import b_lang
    checkout = Path(b_lang.__file__).resolve().parents[1]
    revision = subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD"], text=True).strip()
    if revision != B_COMMIT or subprocess.run(["git", "-C", checkout, "diff", "--quiet", "HEAD",
                                                "--", "b_lang", "b_examples", "dotnet"]).returncode:
        p.error(f"Install B editable from a clean worktree at {B_COMMIT}")
    versions = tool_versions()
    versions["B"] = revision
    versions["npm_packages"] = {pkg: json.loads((modules / pkg / "package.json").read_text())["version"]
                                for pkg in ("fastest-levenshtein", "semver", "@types/node")}
    rows = []
    for replica in range(1, 4):
        row = measure(SIBLING / args.task, f"{args.language}{replica}", modules)
        rows.append(row)
        print(row["task"], row["solver"], row["outcomes"], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"tools": versions, "rows": rows}, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
