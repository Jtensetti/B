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
	SizeKB  int64  `json:"size_kb"`
}

type Output struct {
	Total              int     `json:"total"`
	Eligible           int     `json:"eligible"`
	Oversize           int     `json:"oversize"`
	TotalKB            int64   `json:"total_kb"`
	MaxKB              int64   `json:"max_kb"`
	ConsecutiveRejects int     `json:"consecutive_rejects"`
	Freeze             bool    `json:"freeze"`
	Exempt             int     `json:"exempt"`
	EligibleKB         int64   `json:"eligible_kb"`
	WithinBudget       bool    `json:"within_budget"`
	Recommended        *string `json:"recommended"`
}

type SemVer struct {
	Major      int
	Minor      int
	Patch      int
	Prerelease string
}

func (v SemVer) String() string {
	return fmt.Sprintf("%d.%d.%d", v.Major, v.Minor, v.Patch)
}

type CaretRange struct {
	Min          SemVer
	MaxExclusive SemVer
}

type ParsedArtifact struct {
	Norm        string
	Pkg         string
	VerRaw      string
	Ver         SemVer
	Channel     string
	SizeKB      int64
	SizeTier    string
	ValidFormat bool
	ValidSemVer bool
}

var normPathPattern = regexp.MustCompile(`^[a-z0-9-]+/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$`)

func isValidChannel(channel string) bool {
	switch channel {
	case "stable", "beta", "lts":
		return true
	default:
		return false
	}
}

func classifySizeTier(sizeKB int64) string {
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

func parseStrictUint(s string) (int, bool) {
	if len(s) == 0 {
		return 0, false
	}
	if len(s) > 1 && s[0] == '0' {
		return 0, false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return 0, false
		}
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return 0, false
	}
	return n, true
}

func isValidPrerelease(pre string) bool {
	if pre == "" {
		return false
	}
	parts := strings.Split(pre, ".")
	for _, part := range parts {
		if len(part) == 0 {
			return false
		}
		allDigits := true
		for i := 0; i < len(part); i++ {
			c := part[i]
			isDigit := c >= '0' && c <= '9'
			isAlpha := (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '-'
			if !isDigit && !isAlpha {
				return false
			}
			if !isDigit {
				allDigits = false
			}
		}
		if allDigits && len(part) > 1 && part[0] == '0' {
			return false
		}
	}
	return true
}

func parseSemVer(raw string) (SemVer, bool) {
	core := raw
	prerelease := ""
	if idx := strings.IndexByte(raw, '-'); idx != -1 {
		core = raw[:idx]
		prerelease = raw[idx+1:]
		if !isValidPrerelease(prerelease) {
			return SemVer{}, false
		}
	}

	parts := strings.Split(core, ".")
	if len(parts) != 3 {
		return SemVer{}, false
	}
	major, ok := parseStrictUint(parts[0])
	if !ok {
		return SemVer{}, false
	}
	minor, ok := parseStrictUint(parts[1])
	if !ok {
		return SemVer{}, false
	}
	patch, ok := parseStrictUint(parts[2])
	if !ok {
		return SemVer{}, false
	}

	return SemVer{
		Major:      major,
		Minor:      minor,
		Patch:      patch,
		Prerelease: prerelease,
	}, true
}

func compareCore(a, b SemVer) int {
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

func parseCaretRange(rangeStr string) (CaretRange, bool) {
	s := strings.TrimSpace(rangeStr)
	if !strings.HasPrefix(s, "^") {
		return CaretRange{}, false
	}
	base, ok := parseSemVer(strings.TrimSpace(s[1:]))
	if !ok || base.Prerelease != "" {
		return CaretRange{}, false
	}

	var maxExcl SemVer
	switch {
	case base.Major > 0:
		maxExcl = SemVer{Major: base.Major + 1, Minor: 0, Patch: 0}
	case base.Minor > 0:
		maxExcl = SemVer{Major: 0, Minor: base.Minor + 1, Patch: 0}
	default:
		maxExcl = SemVer{Major: 0, Minor: 0, Patch: base.Patch + 1}
	}

	return CaretRange{
		Min:          base,
		MaxExclusive: maxExcl,
	}, true
}

func (r CaretRange) Satisfies(v SemVer) bool {
	if v.Prerelease != "" {
		return false
	}
	return compareCore(v, r.Min) >= 0 && compareCore(v, r.MaxExclusive) < 0
}

func parseArtifact(a Artifact) ParsedArtifact {
	res := ParsedArtifact{
		Channel:  a.Channel,
		SizeKB:   a.SizeKB,
		SizeTier: classifySizeTier(a.SizeKB),
	}

	decoded, err := url.PathUnescape(a.RawPath)
	if err != nil {
		return res
	}

	norm := path.Clean(decoded)
	res.Norm = norm
	res.Pkg = path.Dir(norm)
	res.VerRaw = path.Base(norm)

	if !normPathPattern.MatchString(norm) || !isValidChannel(a.Channel) {
		return res
	}
	res.ValidFormat = true

	if sv, ok := parseSemVer(res.VerRaw); ok {
		res.Ver = sv
		res.ValidSemVer = true
	}
	return res
}

func isLTSSecurityExempt(p ParsedArtifact) bool {
	return p.ValidFormat &&
		p.Channel == "lts" &&
		strings.Contains(p.Pkg, "security") &&
		p.ValidSemVer &&
		p.Ver.Prerelease == "" &&
		p.SizeTier != "oversize"
}

func evaluate(in Input) Output {
	caret, validRange := parseCaretRange(in.MinRange)

	out := Output{
		Total: len(in.Artifacts),
	}

	prevRejected := false
	hasRecommended := false
	var bestVer SemVer

	for i, artifact := range in.Artifacts {
		out.TotalKB += artifact.SizeKB
		if i == 0 || artifact.SizeKB > out.MaxKB {
			out.MaxKB = artifact.SizeKB
		}

		parsed := parseArtifact(artifact)
		if parsed.SizeTier == "oversize" {
			out.Oversize++
		}
		normalEligible := parsed.ValidFormat && parsed.ValidSemVer && parsed.SizeTier != "oversize" && validRange && caret.Satisfies(parsed.Ver)
		exemptOnly := !normalEligible && isLTSSecurityExempt(parsed)
		eligible := normalEligible || exemptOnly
		if exemptOnly {
			out.Exempt++
		}
		if eligible {
			out.Eligible++
			out.EligibleKB += artifact.SizeKB
			if !hasRecommended || compareCore(parsed.Ver, bestVer) > 0 {
				bestVer = parsed.Ver
				hasRecommended = true
			}
		} else if i > 0 && prevRejected {
			out.ConsecutiveRejects++
		}
		prevRejected = !eligible
	}

	out.Freeze = out.ConsecutiveRejects >= 2
	out.WithinBudget = float64(out.EligibleKB) <= in.BudgetMB*kbPerMB
	if hasRecommended {
		rec := bestVer.String()
		out.Recommended = &rec
	}
	return out
}

func main() {
	var input Input
	if err := json.NewDecoder(os.Stdin).Decode(&input); err != nil {
		fmt.Fprintf(os.Stderr, "failed to decode input JSON: %v\n", err)
		os.Exit(1)
	}

	output := evaluate(input)
	if err := json.NewEncoder(os.Stdout).Encode(output); err != nil {
		fmt.Fprintf(os.Stderr, "failed to encode output JSON: %v\n", err)
		os.Exit(1)
	}
}
