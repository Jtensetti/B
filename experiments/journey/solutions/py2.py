"""Resolve npm version ranges against available versions (port of node-semver 7)."""
import json
import re
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

MAX_LENGTH = 256
MAX_SAFE_INTEGER = 9007199254740991
MAX_SAFE_BUILD_LENGTH = MAX_LENGTH - 6

# JS \s and String.prototype.trim whitespace set
WS = "\t\n\v\f\r \u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
WSCLASS = "[" + WS.replace("\t", "\\t").replace("\n", "\\n").replace("\v", "\\v").replace("\f", "\\f").replace("\r", "\\r") + "]"
LDN = "[a-zA-Z0-9-]"


def js_trim(s: str) -> str:
    return s.strip(WS)


def make_safe(value: str) -> str:
    for token, mx in (("\\s", 1), ("\\d", MAX_LENGTH), (LDN, MAX_SAFE_BUILD_LENGTH)):
        value = value.replace(token + "*", "%s{0,%d}" % (token, mx))
        value = value.replace(token + "+", "%s{1,%d}" % (token, mx))
    return value


SRC: Dict[str, str] = {}
RE: Dict[str, "re.Pattern[str]"] = {}


def token(name: str, value: str) -> None:
    SRC[name] = value
    safe = make_safe(value).replace("[v=\\s]", "[v=" + WSCLASS[1:-1] + "]")
    safe = safe.replace("\\s", WSCLASS).replace("\\d", "[0-9]")
    safe = safe.replace("$", "\\Z")
    RE[name] = re.compile(safe)


token("NUMERICIDENTIFIER", "0|[1-9]\\d*")
token("NONNUMERICIDENTIFIER", "\\d*[a-zA-Z-]%s*" % LDN)
token("MAINVERSION", "(%s)\\.(%s)\\.(%s)" % ((SRC["NUMERICIDENTIFIER"],) * 3))
token("PRERELEASEIDENTIFIER", "(?:%s|%s)" % (SRC["NONNUMERICIDENTIFIER"], SRC["NUMERICIDENTIFIER"]))
token("PRERELEASE", "(?:-(%s(?:\\.%s)*))" % (SRC["PRERELEASEIDENTIFIER"], SRC["PRERELEASEIDENTIFIER"]))
token("BUILDIDENTIFIER", LDN + "+")
token("BUILD", "(?:\\+(%s(?:\\.%s)*))" % (SRC["BUILDIDENTIFIER"], SRC["BUILDIDENTIFIER"]))
token("FULLPLAIN", "v?%s%s?%s?" % (SRC["MAINVERSION"], SRC["PRERELEASE"], SRC["BUILD"]))
token("FULL", "^%s$" % SRC["FULLPLAIN"])
token("GTLT", "((?:<|>)?=?)")
token("XRANGEIDENTIFIER", SRC["NUMERICIDENTIFIER"] + "|x|X|\\*")
token("XRANGEPLAIN", "[v=\\s]*(%s)(?:\\.(%s)(?:\\.(%s)(?:%s)?%s?)?)?" % (
    SRC["XRANGEIDENTIFIER"], SRC["XRANGEIDENTIFIER"], SRC["XRANGEIDENTIFIER"], SRC["PRERELEASE"], SRC["BUILD"]))
token("XRANGE", "^%s\\s*%s$" % (SRC["GTLT"], SRC["XRANGEPLAIN"]))
token("LONETILDE", "(?:~>?)")
token("TILDETRIM", "(\\s*)%s\\s+" % SRC["LONETILDE"])
token("TILDE", "^%s%s$" % (SRC["LONETILDE"], SRC["XRANGEPLAIN"]))
token("LONECARET", "(?:\\^)")
token("CARETTRIM", "(\\s*)%s\\s+" % SRC["LONECARET"])
token("CARET", "^%s%s$" % (SRC["LONECARET"], SRC["XRANGEPLAIN"]))
token("COMPARATOR", "^%s\\s*(%s)$|^$" % (SRC["GTLT"], SRC["FULLPLAIN"]))
token("NUMERICIDENTIFIERLOOSE", "\\d+")
token("MAINVERSIONLOOSE", "(%s)\\.(%s)\\.(%s)" % ((SRC["NUMERICIDENTIFIERLOOSE"],) * 3))
token("PRERELEASEIDENTIFIERLOOSE", "(?:%s|%s)" % (SRC["NONNUMERICIDENTIFIER"], SRC["NUMERICIDENTIFIERLOOSE"]))
token("PRERELEASELOOSE", "(?:-?(%s(?:\\.%s)*))" % (SRC["PRERELEASEIDENTIFIERLOOSE"], SRC["PRERELEASEIDENTIFIERLOOSE"]))
token("LOOSEPLAIN", "[v=\\s]*%s%s?%s?" % (SRC["MAINVERSIONLOOSE"], SRC["PRERELEASELOOSE"], SRC["BUILD"]))
token("COMPARATORTRIM", "(\\s*)%s\\s*(%s|%s)" % (SRC["GTLT"], SRC["LOOSEPLAIN"], SRC["XRANGEPLAIN"]))
token("HYPHENRANGE", "^\\s*(%s)\\s+-\\s+(%s)\\s*$" % (SRC["XRANGEPLAIN"], SRC["XRANGEPLAIN"]))
token("STAR", "(<|>)?=?\\s*\\*")
token("GTE0", "^\\s*>=\\s*0\\.0\\.0\\s*$")
BUILDSTRIP = re.compile(SRC["BUILD"])
SPACES = re.compile(WSCLASS + "+")


class SemVer:
    def __init__(self, version: str) -> None:
        if len(version) > MAX_LENGTH:
            raise ValueError("too long")
        m = RE["FULL"].match(js_trim(version))
        if not m:
            raise ValueError("invalid version")
        self.version_nums: Tuple[int, int, int] = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        for n in self.version_nums:
            if n > MAX_SAFE_INTEGER:
                raise ValueError("too big")
        self.prerelease: List[Any] = []
        if m.group(4):
            for idn in m.group(4).split("."):
                if re.fullmatch("[0-9]+", idn):
                    n = int(idn)
                    self.prerelease.append(n if n < MAX_SAFE_INTEGER else idn)
                else:
                    self.prerelease.append(idn)
        self.version = "%d.%d.%d" % self.version_nums
        if self.prerelease:
            self.version += "-" + ".".join(str(x) for x in self.prerelease)

    def compare(self, other: "SemVer") -> int:
        if self.version_nums != other.version_nums:
            return -1 if self.version_nums < other.version_nums else 1
        a, b = self.prerelease, other.prerelease
        if a and not b:
            return -1
        if not a and b:
            return 1
        i = 0
        while True:
            x = a[i] if i < len(a) else None
            y = b[i] if i < len(b) else None
            if x is None and y is None:
                return 0
            if y is None:
                return 1
            if x is None:
                return -1
            if x == y:
                i += 1
                continue
            return compare_ids(x, y)


def compare_ids(a: Any, b: Any) -> int:
    if isinstance(a, int) and isinstance(b, int):
        return 0 if a == b else (-1 if a < b else 1)
    anum = bool(re.fullmatch("[0-9]+", str(a)))
    bnum = bool(re.fullmatch("[0-9]+", str(b)))
    if anum and bnum:
        a, b = float(a), float(b)
    if a == b:
        return 0
    if anum and not bnum:
        return -1
    if bnum and not anum:
        return 1
    return -1 if a < b else 1


def cmp_op(v: SemVer, op: str, c: SemVer) -> bool:
    r = v.compare(c)
    if op in ("", "=", "=="):
        return r == 0
    if op == ">":
        return r > 0
    if op == ">=":
        return r >= 0
    if op == "<":
        return r < 0
    if op == "<=":
        return r <= 0
    raise ValueError("bad op")


class Comparator:
    def __init__(self, comp: str) -> None:
        comp = " ".join(re.split(WSCLASS + "+", js_trim(comp)))
        m = RE["COMPARATOR"].match(comp)
        if not m:
            raise ValueError("invalid comparator")
        op = m.group(1) if m.group(1) is not None else ""
        self.operator = "" if op == "=" else op
        self.semver: Optional[SemVer] = SemVer(m.group(2)) if m.group(2) else None
        self.value = "" if self.semver is None else self.operator + self.semver.version

    def test(self, v: SemVer) -> bool:
        if self.semver is None:
            return True
        return cmp_op(v, self.operator, self.semver)


def is_x(i: Optional[str]) -> bool:
    return (not i) or i.lower() == "x" or i == "*"


def g(s: Optional[str]) -> str:
    return s if s is not None else ""


def replace_tilde(comp: str) -> str:
    def f(m: "re.Match[str]") -> str:
        M, mi, p, pr = m.group(1), m.group(2), m.group(3), m.group(4)
        if is_x(M):
            return ""
        if is_x(mi):
            return ">=%s.0.0 <%d.0.0-0" % (M, int(M) + 1)
        if is_x(p):
            return ">=%s.%s.0 <%s.%d.0-0" % (M, mi, M, int(mi) + 1)
        if pr:
            return ">=%s.%s.%s-%s <%s.%d.0-0" % (M, mi, p, pr, M, int(mi) + 1)
        return ">=%s.%s.%s <%s.%d.0-0" % (M, mi, p, M, int(mi) + 1)
    return RE["TILDE"].sub(f, comp, count=1)


def replace_caret(comp: str) -> str:
    def f(m: "re.Match[str]") -> str:
        M, mi, p, pr = m.group(1), m.group(2), m.group(3), m.group(4)
        if is_x(M):
            return ""
        if is_x(mi):
            return ">=%s.0.0 <%d.0.0-0" % (M, int(M) + 1)
        if is_x(p):
            if M == "0":
                return ">=%s.%s.0 <%s.%d.0-0" % (M, mi, M, int(mi) + 1)
            return ">=%s.%s.0 <%d.0.0-0" % (M, mi, int(M) + 1)
        pre = "-" + pr if pr else ""
        if M == "0":
            if mi == "0":
                return ">=%s.%s.%s%s <%s.%s.%d-0" % (M, mi, p, pre, M, mi, int(p) + 1)
            return ">=%s.%s.%s%s <%s.%d.0-0" % (M, mi, p, pre, M, int(mi) + 1)
        return ">=%s.%s.%s%s <%d.0.0-0" % (M, mi, p, pre, int(M) + 1)
    return RE["CARET"].sub(f, comp, count=1)


def replace_xrange(comp: str) -> str:
    comp = js_trim(comp)

    def f(m: "re.Match[str]") -> str:
        ret = m.group(0)
        gtlt, M, mi, p = g(m.group(1)), m.group(2), m.group(3), m.group(4)
        if (is_x(M) and not is_x(mi)) or (is_x(mi) and p and not is_x(p)):
            return comp
        xM = is_x(M)
        xm = xM or is_x(mi)
        xp = xm or is_x(p)
        any_x = xp
        if gtlt == "=" and any_x:
            gtlt = ""
        pr = ""
        if xM:
            if gtlt in (">", "<"):
                return "<0.0.0-0"
            return "*"
        if gtlt and any_x:
            Mn: int = int(M)
            mn: int = 0 if xm else int(mi)
            pn = 0
            if gtlt == ">":
                gtlt = ">="
                if xm:
                    Mn += 1
                    mn = 0
                else:
                    mn += 1
            elif gtlt == "<=":
                gtlt = "<"
                if xm:
                    Mn += 1
                else:
                    mn += 1
            if gtlt == "<":
                pr = "-0"
            return "%s%d.%d.%d%s" % (gtlt, Mn, mn, pn, pr)
        if xm:
            return ">=%s.0.0 <%d.0.0-0" % (M, int(M) + 1)
        if xp:
            return ">=%s.%s.0 <%s.%d.0-0" % (M, mi, M, int(mi) + 1)
        return ret
    return RE["XRANGE"].sub(f, comp, count=1)


def hyphen_replace(m: "re.Match[str]") -> str:
    fr, fM, fm, fp, fpr = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
    to, tM, tm, tp, tpr = m.group(7), m.group(8), m.group(9), m.group(10), m.group(11)
    if is_x(fM):
        fr = ""
    elif is_x(fm):
        fr = ">=%s.0.0" % fM
    elif is_x(fp):
        fr = ">=%s.%s.0" % (fM, fm)
    elif fpr:
        fr = ">=" + fr
    else:
        fr = ">=" + fr
    if is_x(tM):
        to = ""
    elif is_x(tm):
        to = "<%d.0.0-0" % (int(tM) + 1)
    elif is_x(tp):
        to = "<%s.%d.0-0" % (tM, int(tm) + 1)
    elif tpr:
        to = "<=%s.%s.%s-%s" % (tM, tm, tp, tpr)
    else:
        to = "<=" + to
    return js_trim("%s %s" % (fr, to))


def parse_comparator(comp: str) -> str:
    comp = BUILDSTRIP.sub("", comp)
    comp = " ".join(replace_caret(c) for c in re.split(WSCLASS + "+", js_trim(comp)))
    comp = " ".join(replace_tilde(c) for c in re.split(WSCLASS + "+", js_trim(comp)))
    comp = " ".join(replace_xrange(c) for c in re.split(WSCLASS + "+", comp))
    return RE["STAR"].sub("", js_trim(comp))


def parse_range(rng: str) -> List[Comparator]:
    rng = BUILDSTRIP.sub("", rng)
    rng = RE["HYPHENRANGE"].sub(hyphen_replace, rng, count=1)
    rng = RE["COMPARATORTRIM"].sub(lambda m: g(m.group(1)) + g(m.group(2)) + g(m.group(3)), rng)
    rng = RE["TILDETRIM"].sub(lambda m: g(m.group(1)) + "~", rng)
    rng = RE["CARETTRIM"].sub(lambda m: g(m.group(1)) + "^", rng)
    parts = " ".join(parse_comparator(c) for c in rng.split(" "))
    lst = [RE["GTE0"].sub("", js_trim(c)) for c in re.split(WSCLASS + "+", parts)]
    comps = [Comparator(c) for c in lst]
    seen: Dict[str, Comparator] = {}
    for c in comps:
        if c.value == "<0.0.0-0":
            return [c]
        seen[c.value] = c
    if len(seen) > 1 and "" in seen:
        del seen[""]
    return list(seen.values())


class Range:
    def __init__(self, rng: str) -> None:
        raw = SPACES.sub(" ", js_trim(rng))
        sets = [parse_range(js_trim(r)) for r in raw.split("||")]
        sets = [s for s in sets if s]
        if not sets:
            raise ValueError("invalid range")
        if len(sets) > 1:
            first = sets[0]
            sets = [s for s in sets if s[0].value != "<0.0.0-0"]
            if not sets:
                sets = [first]
            elif len(sets) > 1:
                for s in sets:
                    if len(s) == 1 and s[0].value == "":
                        sets = [s]
                        break
        self.set = sets

    def test(self, version: str) -> bool:
        if not version:
            return False
        try:
            v = SemVer(version)
        except ValueError:
            return False
        return any(self._test_set(s, v) for s in self.set)

    @staticmethod
    def _test_set(s: List[Comparator], v: SemVer) -> bool:
        if not all(c.test(v) for c in s):
            return False
        if v.prerelease:
            for c in s:
                if c.semver is None:
                    continue
                if c.semver.prerelease and c.semver.version_nums == v.version_nums:
                    return True
            return False
        return True


def max_tag(versions: List[Any], allow_pre: bool) -> Optional[str]:
    best: Optional[str] = None
    best_sv: Optional[SemVer] = None
    for v in versions:
        if not isinstance(v, str):
            continue
        try:
            sv = SemVer(v)
        except ValueError:
            continue
        if sv.prerelease and not allow_pre:
            continue
        if best_sv is None or best_sv.compare(sv) == -1:
            best, best_sv = v, sv
    return best


def max_satisfying(versions: List[Any], rng: Any) -> Optional[str]:
    if not isinstance(rng, str):
        return None
    try:
        r = Range(rng)
    except (ValueError, RecursionError):
        return None
    best: Optional[str] = None
    best_sv: Optional[SemVer] = None
    for v in versions:
        if not isinstance(v, str) or not r.test(v):
            continue
        sv = SemVer(v)
        if sv.prerelease:
            continue
        if best_sv is None or best_sv.compare(sv) == -1:
            best, best_sv = v, sv
    return best


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def suggest(name: str, candidates: List[str]) -> Optional[str]:
    best: Optional[str] = None
    best_d = 3
    for c in sorted(candidates):
        d = levenshtein(name, c)
        if d < best_d:
            best, best_d = c, d
    return best


def clean(v: Any) -> Optional[str]:
    if not isinstance(v, str):
        return None
    try:
        return SemVer(re.sub("^[=v]+", "", js_trim(v))).version
    except ValueError:
        return None


def main() -> None:
    data = json.loads(sys.stdin.readline() if False else sys.stdin.read())
    requires: Dict[str, Any] = data.get("requires") or {}
    raw_available: Dict[str, Any] = data.get("available") or {}
    available: Dict[str, Any] = {}
    for k, lst in raw_available.items():
        if isinstance(lst, list):
            seen: Dict[str, None] = {}
            for x in lst:
                c = clean(x)
                if c is not None:
                    seen[c] = None
            available[k] = list(seen)
        else:
            available[k] = lst
    pins: Dict[str, Any] = {k: (clean(v) or v) for k, v in (data.get("pins") or {}).items()}
    resolved: Dict[str, str] = {}
    suggestions: Dict[str, str] = {}
    unresolved: List[str] = []
    for pkg, rng in requires.items():
        vs = available.get(pkg)
        if pkg in pins:
            best = pins[pkg] if isinstance(vs, list) and pins[pkg] in vs else None
        elif rng in ("latest", "next") and isinstance(vs, list):
            best = max_tag(vs, rng == "next")
        else:
            best = max_satisfying(vs, rng) if isinstance(vs, list) else None
        if best is None:
            unresolved.append(pkg)
            if pkg not in available:
                sug = suggest(pkg, list(available.keys()))
                if sug is not None:
                    suggestions[pkg] = sug
        else:
            resolved[pkg] = best
    unresolved.sort()
    outdated: Dict[str, str] = {}
    for pkg, ver in resolved.items():
        top = max_tag(available[pkg], False)
        if top is None:
            continue
        try:
            if SemVer(top).compare(SemVer(ver)) > 0:
                outdated[pkg] = top
        except ValueError:
            continue
    sys.stdout.write(json.dumps({"resolved": resolved, "unresolved": unresolved, "suggestions": suggestions,
                      "summary": {"resolved": len(resolved), "unresolved": len(unresolved), "suggested": len(suggestions)},
                      "outdated": outdated}) + "\n")


if __name__ == "__main__":
    main()
