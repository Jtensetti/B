package main

// A port of the subset of npm's semver package (node_modules/semver, 7.x)
// needed to decide whether a contract version satisfies a range: full
// versions, the comparators >, >=, <, <=, =, ^, ~, space-separated AND,
// "||" alternatives and "*" / "x" for any version. Prerelease versions only
// match a comparator set that has a prerelease comparator on the same
// major.minor.patch, as npm does.

import (
	"regexp"
	"strconv"
	"strings"
)

type semVer struct {
	major, minor, patch int
	pre                 []string
}

type comparator struct {
	op  string // "", "=", ">", ">=", "<", "<="
	v   semVer
	any bool
}

var (
	versionRe = regexp.MustCompile(`^[v=]?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$`)
	numericRe = regexp.MustCompile(`^\d+$`)
	partialRe = regexp.MustCompile(`^[v=]?(0|[1-9]\d*)(?:\.(0|[1-9]\d*|[xX*]))?(?:\.(0|[1-9]\d*|[xX*]))?$`)
)

func parseVersion(s string) (semVer, bool) {
	m := versionRe.FindStringSubmatch(strings.TrimSpace(s))
	if m == nil {
		return semVer{}, false
	}
	var v semVer
	v.major, _ = strconv.Atoi(m[1])
	v.minor, _ = strconv.Atoi(m[2])
	v.patch, _ = strconv.Atoi(m[3])
	if m[4] != "" {
		v.pre = strings.Split(m[4], ".")
	}
	return v, true
}

func compareIdent(a, b string) int {
	an, bn := numericRe.MatchString(a), numericRe.MatchString(b)
	switch {
	case an && bn:
		if len(a) != len(b) {
			if len(a) < len(b) {
				return -1
			}
			return 1
		}
		return strings.Compare(a, b)
	case an:
		return -1
	case bn:
		return 1
	}
	return strings.Compare(a, b)
}

func compareVersions(a, b semVer) int {
	for _, p := range [][2]int{{a.major, b.major}, {a.minor, b.minor}, {a.patch, b.patch}} {
		if p[0] != p[1] {
			if p[0] < p[1] {
				return -1
			}
			return 1
		}
	}
	switch {
	case len(a.pre) == 0 && len(b.pre) == 0:
		return 0
	case len(a.pre) == 0:
		return 1
	case len(b.pre) == 0:
		return -1
	}
	for i := 0; i < len(a.pre) && i < len(b.pre); i++ {
		if c := compareIdent(a.pre[i], b.pre[i]); c != 0 {
			return c
		}
	}
	switch {
	case len(a.pre) < len(b.pre):
		return -1
	case len(a.pre) > len(b.pre):
		return 1
	}
	return 0
}

// partial is a parsed comparator operand: n is how many of major, minor and
// patch were given (1 to 3); missing or x/* parts are zero.
type partial struct {
	v semVer
	n int
}

func parsePartial(s string) (partial, bool) {
	if m := versionRe.FindStringSubmatch(s); m != nil {
		v, ok := parseVersion(s)
		return partial{v: v, n: 3}, ok
	}
	m := partialRe.FindStringSubmatch(s)
	if m == nil {
		return partial{}, false
	}
	var p partial
	p.n = 1
	nums := []*int{&p.v.major, &p.v.minor, &p.v.patch}
	for i := 0; i < 3; i++ {
		part := m[i+1]
		if part == "" || part == "x" || part == "X" || part == "*" {
			break
		}
		*nums[i], _ = strconv.Atoi(part)
		p.n = i + 1
	}
	return p, true
}

func zeroPre(v semVer) semVer {
	return semVer{major: v.major, minor: v.minor, patch: v.patch, pre: []string{"0"}}
}

// expand turns one operator and operand into primitive comparators, following
// npm's rules for partial versions and for ^ and ~.
func expand(op string, p partial) []comparator {
	v := p.v
	lower := v // partial operands carry no prerelease, so this is the bound as written
	switch op {
	case "", "=":
		if p.n == 3 {
			return []comparator{{op: "=", v: v}}
		}
		return []comparator{{op: ">=", v: lower}, {op: "<", v: upperOf(p)}}
	case ">=":
		return []comparator{{op: ">=", v: lower}}
	case ">":
		if p.n == 3 {
			return []comparator{{op: ">", v: v}}
		}
		return []comparator{{op: ">=", v: upperOf(p.withNoPreUpper())}}
	case "<":
		if p.n == 3 {
			return []comparator{{op: "<", v: v}}
		}
		return []comparator{{op: "<", v: zeroPre(lower)}}
	case "<=":
		if p.n == 3 {
			return []comparator{{op: "<=", v: v}}
		}
		return []comparator{{op: "<", v: upperOf(p)}}
	case "^":
		if p.n == 3 {
			switch {
			case v.major > 0:
				return []comparator{{op: ">=", v: lower}, {op: "<", v: zeroPre(semVer{major: v.major + 1})}}
			case v.minor > 0:
				return []comparator{{op: ">=", v: lower}, {op: "<", v: zeroPre(semVer{minor: v.minor + 1})}}
			default:
				return []comparator{{op: ">=", v: lower}, {op: "<", v: zeroPre(semVer{patch: v.patch + 1})}}
			}
		}
		if p.n == 2 && v.major == 0 {
			return []comparator{{op: ">=", v: lower}, {op: "<", v: zeroPre(semVer{minor: v.minor + 1})}}
		}
		return []comparator{{op: ">=", v: lower}, {op: "<", v: zeroPre(semVer{major: v.major + 1})}}
	case "~":
		if p.n == 1 {
			return []comparator{{op: ">=", v: lower}, {op: "<", v: zeroPre(semVer{major: v.major + 1})}}
		}
		return []comparator{{op: ">=", v: lower}, {op: "<", v: zeroPre(semVer{major: v.major, minor: v.minor + 1})}}
	}
	return nil
}

// upperOf is the exclusive bound for a partial: N -> (N+1).0.0-0, N.M -> N.(M+1).0-0.
func upperOf(p partial) semVer {
	if p.n == 1 {
		return zeroPre(semVer{major: p.v.major + 1})
	}
	return zeroPre(semVer{major: p.v.major, minor: p.v.minor + 1})
}

// withNoPreUpper returns the partial used by ">" on a partial: ">N" means ">=(N+1).0.0"
// and ">N.M" means ">=N.(M+1).0". Expressed as a partial whose upper bound is that version.
func (p partial) withNoPreUpper() partial {
	if p.n == 1 {
		return partial{v: semVer{major: p.v.major + 1}, n: 1}
	}
	return partial{v: semVer{major: p.v.major, minor: p.v.minor + 1}, n: 2}
}

// parseComparators turns one AND-set such as ">=3.0.0 <4" into primitive
// comparators. ok is false when the set is not a valid range.
func parseComparators(set string) ([]comparator, bool) {
	tokens := strings.Fields(set)
	var out []comparator
	for i := 0; i < len(tokens); i++ {
		t := tokens[i]
		// Operators may be separated from their version by a space (">= 3.0.0").
		if (t == ">" || t == ">=" || t == "<" || t == "<=" || t == "=" || t == "^" || t == "~") && i+1 < len(tokens) {
			t += tokens[i+1]
			i++
		}
		if t == "*" || t == "x" || t == "X" {
			out = append(out, comparator{any: true})
			continue
		}
		op := ""
		rest := t
		for _, candidate := range []string{">=", "<=", ">", "<", "=", "^", "~"} {
			if strings.HasPrefix(t, candidate) {
				op = candidate
				rest = t[len(candidate):]
				break
			}
		}
		p, ok := parsePartial(rest)
		if !ok {
			return nil, false
		}
		out = append(out, expand(op, p)...)
	}
	return out, true
}

func (c comparator) test(v semVer) bool {
	if c.any {
		return true
	}
	r := compareVersions(v, c.v)
	switch c.op {
	case "", "=":
		return r == 0
	case ">":
		return r > 0
	case ">=":
		return r >= 0
	case "<":
		return r < 0
	case "<=":
		return r <= 0
	}
	return false
}

func matchSet(v semVer, comps []comparator) bool {
	if len(v.pre) > 0 {
		allowed := false
		for _, c := range comps {
			if !c.any && len(c.v.pre) > 0 && c.v.major == v.major && c.v.minor == v.minor && c.v.patch == v.patch {
				allowed = true
				break
			}
		}
		if !allowed {
			return false
		}
	}
	for _, c := range comps {
		if !c.test(v) {
			return false
		}
	}
	return true
}

// satisfies reports whether version satisfies the semver range, like
// npm's semver.satisfies. An invalid version or range does not satisfy.
func satisfies(version, rng string) bool {
	v, ok := parseVersion(version)
	if !ok {
		return false
	}
	for _, set := range strings.Split(rng, "||") {
		comps, ok := parseComparators(strings.TrimSpace(set))
		if !ok {
			continue
		}
		if matchSet(v, comps) {
			return true
		}
	}
	return false
}
