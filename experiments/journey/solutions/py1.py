"""Resolve npm-style version ranges, mirroring node-semver 7 (default options)."""
import json
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

MAX_LENGTH = 256
MAX_SAFE_INTEGER = 9007199254740991
MAX_SAFE_BUILD_LENGTH = MAX_LENGTH - 6

SRC: Dict[str, str] = {}
RE: Dict[str, "re.Pattern[str]"] = {}


def _make_safe(value: str) -> str:
    for token, mx in (("\\s", 1), ("\\d", MAX_LENGTH), ("[a-zA-Z0-9-]", MAX_SAFE_BUILD_LENGTH)):
        value = value.replace(token + "*", "%s{0,%d}" % (token, mx))
        value = value.replace(token + "+", "%s{1,%d}" % (token, mx))
    return value


def _token(name: str, value: str, is_global: bool = False) -> None:
    SRC[name] = value
    safe = _make_safe(value).replace("\\d", "[0-9]").replace("$", "\\Z")
    RE[name] = re.compile(safe)


LDN = "[a-zA-Z0-9-]"
_token("NUMERICIDENTIFIER", "0|[1-9]\\d*")
_token("NONNUMERICIDENTIFIER", "\\d*[a-zA-Z-]" + LDN + "*")
_token("MAINVERSION", "(%s)\\.(%s)\\.(%s)" % ((SRC["NUMERICIDENTIFIER"],) * 3))
_token("PRERELEASEIDENTIFIER", "(?:%s|%s)" % (SRC["NONNUMERICIDENTIFIER"], SRC["NUMERICIDENTIFIER"]))
_token("PRERELEASE", "(?:-(%s(?:\\.%s)*))" % (SRC["PRERELEASEIDENTIFIER"], SRC["PRERELEASEIDENTIFIER"]))
_token("BUILDIDENTIFIER", LDN + "+")
_token("BUILD", "(?:\\+(%s(?:\\.%s)*))" % (SRC["BUILDIDENTIFIER"], SRC["BUILDIDENTIFIER"]))
_token("FULLPLAIN", "v?%s%s?%s?" % (SRC["MAINVERSION"], SRC["PRERELEASE"], SRC["BUILD"]))
_token("FULL", "^%s$" % SRC["FULLPLAIN"])
_token("NUMERICIDENTIFIERLOOSE", "\\d+")
_token("PRERELEASEIDENTIFIERLOOSE", "(?:%s|%s)" % (SRC["NONNUMERICIDENTIFIER"], SRC["NUMERICIDENTIFIERLOOSE"]))
_token("PRERELEASELOOSE", "(?:-?(%s(?:\\.%s)*))" % (SRC["PRERELEASEIDENTIFIERLOOSE"], SRC["PRERELEASEIDENTIFIERLOOSE"]))
_token("MAINVERSIONLOOSE", "(%s)\\.(%s)\\.(%s)" % ((SRC["NUMERICIDENTIFIERLOOSE"],) * 3))
_token("LOOSEPLAIN", "[v=\\s]*%s%s?%s?" % (SRC["MAINVERSIONLOOSE"], SRC["PRERELEASELOOSE"], SRC["BUILD"]))
_token("GTLT", "((?:<|>)?=?)")
_token("XRANGEIDENTIFIER", SRC["NUMERICIDENTIFIER"] + "|x|X|\\*")
_token(
    "XRANGEPLAIN",
    "[v=\\s]*(%s)(?:\\.(%s)(?:\\.(%s)(?:%s)?%s?)?)?"
    % (SRC["XRANGEIDENTIFIER"], SRC["XRANGEIDENTIFIER"], SRC["XRANGEIDENTIFIER"], SRC["PRERELEASE"], SRC["BUILD"]),
)
_token("XRANGE", "^%s\\s*%s$" % (SRC["GTLT"], SRC["XRANGEPLAIN"]))
_token("LONETILDE", "(?:~>?)")
_token("TILDETRIM", "(\\s*)%s\\s+" % SRC["LONETILDE"], True)
_token("TILDE", "^%s%s$" % (SRC["LONETILDE"], SRC["XRANGEPLAIN"]))
_token("LONECARET", "(?:\\^)")
_token("CARETTRIM", "(\\s*)%s\\s+" % SRC["LONECARET"], True)
_token("CARET", "^%s%s$" % (SRC["LONECARET"], SRC["XRANGEPLAIN"]))
_token("COMPARATOR", "^%s\\s*(%s)$|^$" % (SRC["GTLT"], SRC["FULLPLAIN"]))
_token("COMPARATORTRIM", "(\\s*)%s\\s*(%s|%s)" % (SRC["GTLT"], SRC["LOOSEPLAIN"], SRC["XRANGEPLAIN"]), True)
_token(
    "HYPHENRANGE",
    "^\\s*(%s)\\s+-\\s+(%s)\\s*$" % (SRC["XRANGEPLAIN"], SRC["XRANGEPLAIN"]),
)
_token("STAR", "(<|>)?=?\\s*\\*")
_token("GTE0", "^\\s*>=\\s*0\\.0\\.0\\s*$")
BUILDSTRIPRE = re.compile(SRC["BUILD"].replace("\\d", "[0-9]"))


class SemVer:
    def __init__(self, version: Any) -> None:
        if not isinstance(version, str):
            raise TypeError("Invalid version")
        if len(version) > MAX_LENGTH:
            raise TypeError("too long")
        m = RE["FULL"].match(version.strip())
        if not m:
            raise TypeError("Invalid Version")
        self.major = int(m.group(1))
        self.minor = int(m.group(2))
        self.patch = int(m.group(3))
        for n in (self.major, self.minor, self.patch):
            if n > MAX_SAFE_INTEGER:
                raise TypeError("Invalid component")
        self.prerelease: List[Any] = []
        if m.group(4):
            for ident in m.group(4).split("."):
                if re.fullmatch("[0-9]+", ident) and int(ident) < MAX_SAFE_INTEGER:
                    self.prerelease.append(int(ident))
                else:
                    self.prerelease.append(ident)
        self.version = "%d.%d.%d" % (self.major, self.minor, self.patch)
        if self.prerelease:
            self.version += "-" + ".".join(str(p) for p in self.prerelease)

    def compare(self, other: "SemVer") -> int:
        if other.version == self.version:
            return 0
        a = (self.major, self.minor, self.patch)
        b = (other.major, other.minor, other.patch)
        if a != b:
            return -1 if a < b else 1
        return self.compare_pre(other)

    def compare_pre(self, other: "SemVer") -> int:
        if self.prerelease and not other.prerelease:
            return -1
        if not self.prerelease and other.prerelease:
            return 1
        if not self.prerelease and not other.prerelease:
            return 0
        i = 0
        while True:
            a = self.prerelease[i] if i < len(self.prerelease) else None
            b = other.prerelease[i] if i < len(other.prerelease) else None
            if a is None and b is None:
                return 0
            if b is None:
                return 1
            if a is None:
                return -1
            if a != b or type(a) is not type(b):
                c = compare_identifiers(a, b)
                if c != 0:
                    return c
            i += 1


def compare_identifiers(a: Any, b: Any) -> int:
    if isinstance(a, int) and isinstance(b, int):
        return 0 if a == b else (-1 if a < b else 1)
    anum = isinstance(a, int) or re.fullmatch("[0-9]+", a) is not None
    bnum = isinstance(b, int) or re.fullmatch("[0-9]+", b) is not None
    if anum and bnum:
        a, b = int(a), int(b)
    if a == b:
        return 0
    if anum and not bnum:
        return -1
    if bnum and not anum:
        return 1
    return -1 if a < b else 1


class Comparator:
    def __init__(self, comp: str) -> None:
        comp = " ".join(comp.strip().split())
        m = RE["COMPARATOR"].match(comp)
        if not m:
            raise TypeError("Invalid comparator")
        self.operator = m.group(1) if m.group(1) is not None else ""
        if self.operator == "=":
            self.operator = ""
        self.semver: Optional[SemVer] = None
        if m.group(2):
            self.semver = SemVer(m.group(2))
        self.value = "" if self.semver is None else self.operator + self.semver.version

    def test(self, version: SemVer) -> bool:
        if self.semver is None:
            return True
        c = version.compare(self.semver)
        op = self.operator
        if op == "":
            return c == 0
        if op == ">":
            return c > 0
        if op == ">=":
            return c >= 0
        if op == "<":
            return c < 0
        if op == "<=":
            return c <= 0
        raise TypeError("Invalid operator")


def is_x(s: Optional[str]) -> bool:
    return not s or s.lower() == "x" or s == "*"


def _g(m: "re.Match[str]", i: int) -> Optional[str]:
    return m.group(i)


def replace_tilde(comp: str) -> str:
    def fn(m: "re.Match[str]") -> str:
        M, mi, p, pr = m.group(1), m.group(2), m.group(3), m.group(4)
        if is_x(M):
            return ""
        assert M is not None
        if is_x(mi):
            return ">=%s.0.0 <%d.0.0-0" % (M, int(M) + 1)
        assert mi is not None
        if is_x(p):
            return ">=%s.%s.0 <%s.%d.0-0" % (M, mi, M, int(mi) + 1)
        if pr:
            return ">=%s.%s.%s-%s <%s.%d.0-0" % (M, mi, p, pr, M, int(mi) + 1)
        return ">=%s.%s.%s <%s.%d.0-0" % (M, mi, p, M, int(mi) + 1)

    return RE["TILDE"].sub(fn, comp, count=1)


def replace_caret(comp: str) -> str:
    def fn(m: "re.Match[str]") -> str:
        M, mi, p, pr = m.group(1), m.group(2), m.group(3), m.group(4)
        if is_x(M):
            return ""
        assert M is not None
        if is_x(mi):
            return ">=%s.0.0 <%d.0.0-0" % (M, int(M) + 1)
        assert mi is not None
        if is_x(p):
            if M == "0":
                return ">=%s.%s.0 <%s.%d.0-0" % (M, mi, M, int(mi) + 1)
            return ">=%s.%s.0 <%d.0.0-0" % (M, mi, int(M) + 1)
        assert p is not None
        if pr:
            if M == "0":
                if mi == "0":
                    return ">=%s.%s.%s-%s <%s.%s.%d-0" % (M, mi, p, pr, M, mi, int(p) + 1)
                return ">=%s.%s.%s-%s <%s.%d.0-0" % (M, mi, p, pr, M, int(mi) + 1)
            return ">=%s.%s.%s-%s <%d.0.0-0" % (M, mi, p, pr, int(M) + 1)
        if M == "0":
            if mi == "0":
                return ">=%s.%s.%s <%s.%s.%d-0" % (M, mi, p, M, mi, int(p) + 1)
            return ">=%s.%s.%s <%s.%d.0-0" % (M, mi, p, M, int(mi) + 1)
        return ">=%s.%s.%s <%d.0.0-0" % (M, mi, p, int(M) + 1)

    return RE["CARET"].sub(fn, comp, count=1)


def replace_xrange(comp: str) -> str:
    comp = comp.strip()

    def fn(match: "re.Match[str]") -> str:
        ret = match.group(0)
        gtlt: str = match.group(1) or ""
        M, m, p = match.group(2), match.group(3), match.group(4)
        if (is_x(M) and not is_x(m)) or (is_x(m) and p and not is_x(p)):
            return comp
        xM = is_x(M)
        xm = xM or is_x(m)
        xp = xm or is_x(p)
        any_x = xp
        if gtlt == "=" and any_x:
            gtlt = ""
        pr = ""
        if xM:
            if gtlt == ">" or gtlt == "<":
                ret = "<0.0.0-0"
            else:
                ret = "*"
        elif gtlt and any_x:
            assert M is not None
            mi: int = 0 if xm else int(m or 0)
            pi = 0
            Mi = int(M)
            if gtlt == ">":
                gtlt = ">="
                if xm:
                    Mi += 1
                    mi = 0
                    pi = 0
                else:
                    mi += 1
                    pi = 0
            elif gtlt == "<=":
                gtlt = "<"
                if xm:
                    Mi += 1
                else:
                    mi += 1
            if gtlt == "<":
                pr = "-0"
            ret = "%s%d.%d.%d%s" % (gtlt, Mi, mi, pi, pr)
        elif xm:
            assert M is not None
            ret = ">=%s.0.0 <%d.0.0-0" % (M, int(M) + 1)
        elif xp:
            assert M is not None and m is not None
            ret = ">=%s.%s.0 <%s.%d.0-0" % (M, m, M, int(m) + 1)
        return ret

    return RE["XRANGE"].sub(fn, comp, count=1)


def parse_comparator(comp: str) -> str:
    comp = BUILDSTRIPRE_SUB(comp)
    comp = " ".join(replace_caret(c) for c in re.split(r"\s+", comp.strip()))
    comp = " ".join(replace_tilde(c) for c in re.split(r"\s+", comp.strip()))
    comp = " ".join(replace_xrange(c) for c in re.split(r"\s+", comp))
    comp = RE["STAR"].sub("", comp.strip())
    return comp


def BUILDSTRIPRE_SUB(s: str) -> str:
    return RE_BUILD_SAFE.sub("", s)


RE_BUILD_SAFE = RE["BUILD"]


def hyphen_replace(m: "re.Match[str]") -> str:
    g = m.groups()
    frm, fM, fm, fp, fpr = g[0], g[1], g[2], g[3], g[4]
    to, tM, tm, tp, tpr = g[6], g[7], g[8], g[9], g[10]
    if is_x(fM):
        frm = ""
    elif is_x(fm):
        frm = ">=%s.0.0" % fM
    elif is_x(fp):
        frm = ">=%s.%s.0" % (fM, fm)
    elif fpr:
        frm = ">=%s" % frm
    else:
        frm = ">=%s" % frm
    if is_x(tM):
        to = ""
    elif is_x(tm):
        to = "<%d.0.0-0" % (int(tM) + 1)
    elif is_x(tp):
        to = "<%s.%d.0-0" % (tM, int(tm) + 1)
    elif tpr:
        to = "<=%s.%s.%s-%s" % (tM, tm, tp, tpr)
    else:
        to = "<=%s" % to
    return ("%s %s" % (frm, to)).strip()


def is_null_set(c: Comparator) -> bool:
    return c.value == "<0.0.0-0"


def parse_range(rng: str) -> List[Comparator]:
    rng = BUILDSTRIPRE.sub("", rng)
    rng = RE["HYPHENRANGE"].sub(hyphen_replace, rng, count=1)
    rng = RE["COMPARATORTRIM"].sub(
        lambda m: (m.group(1) or "") + (m.group(2) or "") + (m.group(3) or ""), rng
    )
    rng = RE["TILDETRIM"].sub(lambda m: (m.group(1) or "") + "~", rng)
    rng = RE["CARETTRIM"].sub(lambda m: (m.group(1) or "") + "^", rng)
    parts_l = re.split(r"\s+", " ".join(parse_comparator(c) for c in rng.split(" ")))
    parts_l = [RE["GTE0"].sub("", c.strip()) for c in parts_l]
    comps = [Comparator(c) for c in parts_l]
    rmap: Dict[str, Comparator] = {}
    for c in comps:
        if is_null_set(c):
            return [c]
        rmap[c.value] = c
    if len(rmap) > 1 and "" in rmap:
        del rmap[""]
    return list(rmap.values())


class Range:
    def __init__(self, rng: Any) -> None:
        if not isinstance(rng, str):
            raise TypeError("Invalid range")
        raw = re.sub(r"\s+", " ", rng.strip())
        sets = [parse_range(r.strip()) for r in raw.split("||")]
        sets = [s for s in sets if s]
        if not sets:
            raise TypeError("Invalid SemVer Range")
        if len(sets) > 1:
            first = sets[0]
            sets = [s for s in sets if not is_null_set(s[0])]
            if not sets:
                sets = [first]
            elif len(sets) > 1:
                for c in sets:
                    if len(c) == 1 and c[0].value == "":
                        sets = [c]
                        break
        self.set = sets

    def test(self, v: SemVer) -> bool:
        return any(self._test_set(s, v) for s in self.set)

    @staticmethod
    def _test_set(s: List[Comparator], v: SemVer) -> bool:
        for c in s:
            if not c.test(v):
                return False
        if v.prerelease:
            for c in s:
                if c.semver is None:
                    continue
                if c.semver.prerelease:
                    a = c.semver
                    if (a.major, a.minor, a.patch) == (v.major, v.minor, v.patch):
                        return True
            return False
        return True


def max_satisfying(versions: Any, rng: Any) -> Optional[str]:
    try:
        r = Range(rng)
    except (TypeError, ValueError, RecursionError):
        return None
    best: Optional[str] = None
    best_sv: Optional[SemVer] = None
    if not isinstance(versions, list):
        return None
    for v in versions:
        try:
            sv = SemVer(v)
        except (TypeError, ValueError):
            continue
        if sv.prerelease:
            continue
        if r.test(sv):
            if best_sv is None or best_sv.compare(sv) == -1:
                best = v
                best_sv = sv
    return best


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def suggest(name: str, names: List[str]) -> Optional[str]:
    best: Optional[str] = None
    best_d = 3
    for n in sorted(names):
        d = levenshtein(name, n)
        if d < best_d:
            best, best_d = n, d
    return best


def dist_tag(versions: Any, tag: str) -> Optional[str]:
    best: Optional[str] = None
    best_sv: Optional[SemVer] = None
    if not isinstance(versions, list):
        return None
    for v in versions:
        try:
            sv = SemVer(v)
        except (TypeError, ValueError):
            continue
        if tag == "latest" and sv.prerelease:
            continue
        if best_sv is None or best_sv.compare(sv) == -1:
            best = v
            best_sv = sv
    return best


def clean(version: Any) -> Optional[str]:
    if not isinstance(version, str):
        return None
    try:
        return SemVer(re.sub(r"^[=v]+", "", version.strip())).version
    except (TypeError, ValueError):
        return None


def clean_list(versions: Any) -> Any:
    if not isinstance(versions, list):
        return versions
    out: List[str] = []
    for v in versions:
        c = clean(v)
        if c is not None and c not in out:
            out.append(c)
    return out


def resolve(data: Dict[str, Any]) -> Dict[str, Any]:
    requires = data.get("requires") or {}
    available = {k: clean_list(v) for k, v in (data.get("available") or {}).items()}
    pins = {k: (clean(v) or v) for k, v in (data.get("pins") or {}).items()}
    resolved: Dict[str, str] = {}
    unresolved: List[str] = []
    for pkg, rng in requires.items():
        if pkg in pins:
            avail = available.get(pkg)
            best = pins[pkg] if isinstance(avail, list) and pins[pkg] in avail else None
        elif rng in ("latest", "next"):
            best = dist_tag(available.get(pkg), rng)
        else:
            best = max_satisfying(available.get(pkg), rng) if pkg in available else None
        if best is None:
            unresolved.append(pkg)
        else:
            resolved[pkg] = best
    unresolved.sort()
    suggestions: Dict[str, str] = {}
    for pkg in unresolved:
        if pkg not in available:
            sg = suggest(pkg, list(available.keys()))
            if sg is not None:
                suggestions[pkg] = sg
    outdated: Dict[str, str] = {}
    for pkg, ver in resolved.items():
        top = dist_tag(available.get(pkg), "latest")
        if top is None:
            continue
        try:
            if SemVer(ver).compare(SemVer(top)) == -1:
                outdated[pkg] = top
        except (TypeError, ValueError):
            continue
    summary = {
        "resolved": len(resolved),
        "unresolved": len(unresolved),
        "suggested": len(suggestions),
    }
    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "suggestions": suggestions,
        "summary": summary,
        "outdated": outdated,
    }


def main() -> None:
    data = json.loads(sys.stdin.readline())
    sys.stdout.write(json.dumps(resolve(data)) + "\n")


if __name__ == "__main__":
    main()
