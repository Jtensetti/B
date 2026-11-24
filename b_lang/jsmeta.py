"""Static boundaries for synchronous named Node exports."""
import re

from .types import ANY, BError, BOOL, INT, TEXT, Signature, Type, option

POSIX = "node:path/posix"
CATALOG = {
    POSIX: {
        name: Signature((TEXT,) * arity, TEXT)
        for name, arity in (("basename", 1), ("dirname", 1), ("extname", 1),
                            ("normalize", 1), ("join", 2), ("relative", 2))
    },
    "semver": {
        "satisfies": Signature((TEXT, TEXT), BOOL),
        "compare": Signature((TEXT, TEXT), INT),
        "valid": Signature((TEXT,), option(TEXT)),
        "maxSatisfying": Signature((Type("List", (TEXT,)), TEXT), option(TEXT)),
        "minSatisfying": Signature((Type("List", (TEXT,)), TEXT), option(TEXT)),
        "clean": Signature((TEXT,), option(TEXT)),
        "validRange": Signature((TEXT,), option(TEXT)),
        "prerelease": Signature((TEXT,), option(Type("List", (ANY,)))),
        "gt": Signature((TEXT, TEXT), BOOL),
        "gte": Signature((TEXT, TEXT), BOOL),
        "lt": Signature((TEXT, TEXT), BOOL),
        "lte": Signature((TEXT, TEXT), BOOL),
        "eq": Signature((TEXT, TEXT), BOOL),
        "major": Signature((TEXT,), INT),
        "minor": Signature((TEXT,), INT),
        "patch": Signature((TEXT,), INT),
        "sort": Signature((Type("List", (TEXT,)),), Type("List", (TEXT,))),
        "rsort": Signature((Type("List", (TEXT,)),), Type("List", (TEXT,))),
        "diff": Signature((TEXT, TEXT), option(TEXT)),
        "inc": Signature((TEXT, TEXT), option(TEXT)),
        "intersects": Signature((TEXT, TEXT), BOOL),
    },
    "fastest-levenshtein": {
        "distance": Signature((TEXT, TEXT), INT),
        "closest": Signature((TEXT, Type("List", (TEXT,))), TEXT),
    },
}
_PACKAGE = re.compile(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*")


def check_target(name: str):
    if name != POSIX and not _PACKAGE.fullmatch(name):
        raise BError("E_IMPORT", f"Expected {POSIX} or a bare npm package name, got {name!r}")


def check_declaration(module, member, signature):
    if module == POSIX or len(member) != 1 or member[0].startswith("_"):
        raise BError("E_FOREIGN", "Declare a public, directly named export of an npm package")
    def supported(typ):
        return (typ.name in ("Bool", "Text", "Int", "Float")
                or typ.name in ("Option", "List", "Dict") and all(supported(t) for t in typ.args))
    if not all(supported(t) for t in (*signature.params, signature.result)):
        raise BError("E_FOREIGN", "Node declarations require concrete JSON value types")


def provenance(module):
    return {"semver": "curated-semver-7", "fastest-levenshtein": "curated-fastest-levenshtein-1"}.get(
        module, "curated-node-api")


def describe(module):
    check_target(module)
    return {
        "target": "js:" + module, "origin": "static B catalog",
        "provenance": provenance(module) if module in CATALOG else "declaration-required",
        "installed_version_checked": False, "behavior_proven": False,
        "signatures": [
            {"name": name, "parameters": [str(t) for t in sig.params], "result": str(sig.result),
             "min_arity": sig.required}
            for name, sig in sorted(CATALOG.get(module, {}).items())
        ],
    }
