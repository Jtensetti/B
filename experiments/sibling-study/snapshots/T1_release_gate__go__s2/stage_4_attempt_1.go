package main

import (
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"path"
	"regexp"
	"strconv"
	"strings"
)

const kbPerMB = 1024.0

type Input struct {
	MinRange  string     `json:"min_range"`
	BudgetMB  float64    `json:"budget_mb"`
	Artifacts []Artifact `json:"artifacts"`
}

type Artifact struct {
	RawPath string `json:"raw_path"`
	Channel string `json:"channel"`
	SizeKB  int    `json:"size_kb"`
}

type Output struct {
	Total              int  `json:"total"`
	Eligible           int  `json:"eligible"`
	Oversize           int  `json:"oversize"`
	TotalKB            int  `json:"total_kb"`
	MaxKB              int  `json:"max_kb"`
	ConsecutiveRejects int  `json:"consecutive_rejects"`
	Freeze             bool `json:"freeze"`
	Exempt             int  `json:"exempt"`
	EligibleKB         int  `json:"eligible_kb"`
	WithinBudget       bool `json:"within_budget"`
}

type Semver struct {
	Major      int
	Minor      int
	Patch      int
	Prerelease []string
}

func (v Semver) HasPrerelease() bool {
	return len(v.Prerelease) > 0
}

func compareCore(a, b Semver) int {
	if a.Major != b.Major {
		if a.Major < b.Major {
			return -1
		}
		return 1
	}
	if a.Minor != b.Minor {
		if a.Minor < b.Minor {
			return -1
		}
		return 1
	}
	if a.Patch != b.Patch {
		if a.Patch < b.Patch {
			return -1
		}
		return 1
	}
	return 0
}

func isAllDigits(s string) bool {
	if len(s) == 0 {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return true
}

func parseStrictUint(s string) (int, bool) {
	if !isAllDigits(s) {
		return 0, false
	}
	if len(s) > 1 && s[0] == '0' {
		return 0, false
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 0 {
		return 0, false
	}
	return n, true
}

func parseSemver(s string) (Semver, bool) {
	core := s
	var prePart string
	hasPre := false
	if idx := strings.IndexByte(s, '-'); idx >= 0 {
		core = s[:idx]
		prePart = s[idx+1:]
		hasPre = true
	}

	parts := strings.Split(core, ".")
	if len(parts) != 3 {
		return Semver{}, false
	}

	major, ok := parseStrictUint(parts[0])
	if !ok {
		return Semver{}, false
	}
	minor, ok := parseStrictUint(parts[1])
	if !ok {
		return Semver{}, false
	}
	patch, ok := parseStrictUint(parts[2])
	if !ok {
		return Semver{}, false
	}

	var preIDs []string
	if hasPre {
		if prePart == "" {
			return Semver{}, false
		}
		preIDs = strings.Split(prePart, ".")
		for _, id := range preIDs {
			if id == "" {
				return Semver{}, false
			}
			for i := 0; i < len(id); i++ {
				c := id[i]
				isAlphaNum := (c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '-'
				if !isAlphaNum {
					return Semver{}, false
				}
			}
			if isAllDigits(id) && len(id) > 1 && id[0] == '0' {
				return Semver{}, false
			}
		}
	}

	return Semver{
		Major:      major,
		Minor:      minor,
		Patch:      patch,
		Prerelease: preIDs,
	}, true
}

type CaretRange struct {
	Lower Semver
	Upper Semver
}

func parseCaretRange(spec string) (CaretRange, bool) {
	spec = strings.TrimSpace(spec)
	if !strings.HasPrefix(spec, "^") {
		return CaretRange{}, false
	}
	base, ok := parseSemver(spec[1:])
	if !ok || base.HasPrerelease() {
		return CaretRange{}, false
	}

	var upper Semver
	switch {
	case base.Major > 0:
		upper = Semver{Major: base.Major + 1, Minor: 0, Patch: 0}
	case base.Minor > 0:
		upper = Semver{Major: 0, Minor: base.Minor + 1, Patch: 0}
	default:
		upper = Semver{Major: 0, Minor: 0, Patch: base.Patch + 1}
	}

	return CaretRange{
		Lower: base,
		Upper: upper,
	}, true
}

func (r CaretRange) Satisfies(v Semver) bool {
	if v.HasPrerelease() {
		return false
	}
	return compareCore(v, r.Lower) >= 0 && compareCore(v, r.Upper) < 0
}

var validNormPathRe = regexp.MustCompile(`^[a-z0-9-]+/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$`)

func isValidChannel(channel string) bool {
	switch channel {
	case "stable", "beta", "lts":
		return true
	default:
		return false
	}
}

func classifySizeTier(sizeKB int) string {
	switch {
	case sizeKB < 100:
		return "tiny"
	case sizeKB <= 1000:
		return "standard"
	case sizeKB <= 5000:
		return "large"
	default:
		return "oversize"
	}
}

type Evaluation struct {
	Eligible bool
	Exempt   bool
}

func evaluateArtifact(a Artifact, tier string, minRange CaretRange, hasValidRange bool) Evaluation {
	if tier == "oversize" {
		return Evaluation{}
	}
	if !isValidChannel(a.Channel) {
		return Evaluation{}
	}
	decoded, err := url.PathUnescape(a.RawPath)
	if err != nil {
		return Evaluation{}
	}
	norm := path.Clean(decoded)
	if !validNormPathRe.MatchString(norm) {
		return Evaluation{}
	}
	pkg := path.Dir(norm)
	verStr := path.Base(norm)
	ver, ok := parseSemver(verStr)
	if !ok {
		return Evaluation{}
	}
	if hasValidRange && minRange.Satisfies(ver) {
		return Evaluation{Eligible: true}
	}
	if a.Channel == "lts" && strings.Contains(pkg, "security") && !ver.HasPrerelease() {
		return Evaluation{Eligible: true, Exempt: true}
	}
	return Evaluation{}
}

func process(input Input) Output {
	minRange, hasValidRange := parseCaretRange(input.MinRange)

	out := Output{
		Total: len(input.Artifacts),
	}
	prevEligible := true
	for i, a := range input.Artifacts {
		out.TotalKB += a.SizeKB
		if i == 0 || a.SizeKB > out.MaxKB {
			out.MaxKB = a.SizeKB
		}
		tier := classifySizeTier(a.SizeKB)
		if tier == "oversize" {
			out.Oversize++
		}
		eval := evaluateArtifact(a, tier, minRange, hasValidRange)
		if eval.Eligible {
			out.Eligible++
			out.EligibleKB += a.SizeKB
		}
		if eval.Exempt {
			out.Exempt++
		}
		if i > 0 && !prevEligible && !eval.Eligible {
			out.ConsecutiveRejects++
		}
		prevEligible = eval.Eligible
	}
	out.Freeze = out.ConsecutiveRejects >= 2
	out.WithinBudget = float64(out.EligibleKB) <= input.BudgetMB*kbPerMB
	return out
}

func main() {
	var input Input
	if err := json.NewDecoder(os.Stdin).Decode(&input); err != nil {
		fmt.Fprintf(os.Stderr, "failed to decode input JSON: %v\n", err)
		os.Exit(1)
	}

	output := process(input)
	if err := json.NewEncoder(os.Stdout).Encode(output); err != nil {
		fmt.Fprintf(os.Stderr, "failed to encode output JSON: %v\n", err)
		os.Exit(1)
	}
}
