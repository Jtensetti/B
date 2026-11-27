package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"os"
	"path"
	"regexp"
	"strconv"
	"strings"
)

var artifactPathRegex = regexp.MustCompile(`^[a-z0-9-]+/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$`)

type Input struct {
	MinRange  string     `json:"min_range"`
	Artifacts []Artifact `json:"artifacts"`
}

type Artifact struct {
	RawPath string `json:"raw_path"`
	Channel string `json:"channel"`
	SizeKB  int64  `json:"size_kb"`
}

type Output struct {
	Total    int   `json:"total"`
	Eligible int   `json:"eligible"`
	TotalKB  int64 `json:"total_kb"`
	MaxKB    int64 `json:"max_kb"`
}

type SemVer struct {
	Major      int
	Minor      int
	Patch      int
	Prerelease []string
}

func (v SemVer) HasPrerelease() bool {
	return len(v.Prerelease) > 0
}

func (v SemVer) CompareCore(other SemVer) int {
	if v.Major != other.Major {
		if v.Major < other.Major {
			return -1
		}
		return 1
	}
	if v.Minor != other.Minor {
		if v.Minor < other.Minor {
			return -1
		}
		return 1
	}
	if v.Patch != other.Patch {
		if v.Patch < other.Patch {
			return -1
		}
		return 1
	}
	return 0
}

func (v SemVer) Compare(other SemVer) int {
	if cmp := v.CompareCore(other); cmp != 0 {
		return cmp
	}
	if !v.HasPrerelease() && !other.HasPrerelease() {
		return 0
	}
	if !v.HasPrerelease() {
		return 1
	}
	if !other.HasPrerelease() {
		return -1
	}
	limit := len(v.Prerelease)
	if len(other.Prerelease) < limit {
		limit = len(other.Prerelease)
	}
	for i := 0; i < limit; i++ {
		if cmp := comparePrereleaseID(v.Prerelease[i], other.Prerelease[i]); cmp != 0 {
			return cmp
		}
	}
	if len(v.Prerelease) < len(other.Prerelease) {
		return -1
	}
	if len(v.Prerelease) > len(other.Prerelease) {
		return 1
	}
	return 0
}

func comparePrereleaseID(a, b string) int {
	aNum, aIsNum := parseUintStrict(a)
	bNum, bIsNum := parseUintStrict(b)
	switch {
	case aIsNum && bIsNum:
		if aNum < bNum {
			return -1
		}
		if aNum > bNum {
			return 1
		}
		return 0
	case aIsNum && !bIsNum:
		return -1
	case !aIsNum && bIsNum:
		return 1
	default:
		return strings.Compare(a, b)
	}
}

func isAllDigits(s string) bool {
	if s == "" {
		return false
	}
	for i := 0; i < len(s); i++ {
		if s[i] < '0' || s[i] > '9' {
			return false
		}
	}
	return true
}

func parseUintStrict(s string) (int, bool) {
	if !isAllDigits(s) {
		return 0, false
	}
	if len(s) > 1 && s[0] == '0' {
		return 0, false
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return 0, false
	}
	return n, true
}

func parseSemVer(s string) (SemVer, error) {
	var zero SemVer
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
		return zero, errors.New("invalid semver core")
	}

	major, ok := parseUintStrict(parts[0])
	if !ok {
		return zero, errors.New("invalid major version")
	}
	minor, ok := parseUintStrict(parts[1])
	if !ok {
		return zero, errors.New("invalid minor version")
	}
	patch, ok := parseUintStrict(parts[2])
	if !ok {
		return zero, errors.New("invalid patch version")
	}

	var preIDs []string
	if hasPre {
		if prePart == "" {
			return zero, errors.New("empty prerelease")
		}
		preIDs = strings.Split(prePart, ".")
		for _, id := range preIDs {
			if id == "" {
				return zero, errors.New("empty prerelease identifier")
			}
			for i := 0; i < len(id); i++ {
				c := id[i]
				if !((c >= '0' && c <= '9') || (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '-') {
					return zero, errors.New("invalid prerelease character")
				}
			}
			if isAllDigits(id) && len(id) > 1 && id[0] == '0' {
				return zero, errors.New("leading zero in numeric prerelease identifier")
			}
		}
	}

	return SemVer{
		Major:      major,
		Minor:      minor,
		Patch:      patch,
		Prerelease: preIDs,
	}, nil
}

type CaretRange struct {
	Min SemVer
	Max SemVer
}

func parseCaretRange(s string) (CaretRange, error) {
	trimmed := strings.TrimSpace(s)
	if !strings.HasPrefix(trimmed, "^") {
		return CaretRange{}, errors.New("expected caret range")
	}
	minVer, err := parseSemVer(strings.TrimSpace(trimmed[1:]))
	if err != nil {
		return CaretRange{}, err
	}

	var maxVer SemVer
	switch {
	case minVer.Major > 0:
		maxVer = SemVer{Major: minVer.Major + 1, Minor: 0, Patch: 0}
	case minVer.Minor > 0:
		maxVer = SemVer{Major: 0, Minor: minVer.Minor + 1, Patch: 0}
	default:
		maxVer = SemVer{Major: 0, Minor: 0, Patch: minVer.Patch + 1}
	}

	return CaretRange{Min: minVer, Max: maxVer}, nil
}

func (r CaretRange) Satisfies(v SemVer) bool {
	if v.HasPrerelease() {
		if !r.Min.HasPrerelease() || v.CompareCore(r.Min) != 0 {
			return false
		}
	}
	return v.Compare(r.Min) >= 0 && v.Compare(r.Max) < 0
}

func isValidChannel(channel string) bool {
	switch channel {
	case "stable", "beta", "lts":
		return true
	default:
		return false
	}
}

func parseArtifactPath(rawPath string) (norm, pkg, ver string, ok bool) {
	decoded, err := url.PathUnescape(rawPath)
	if err != nil {
		return "", "", "", false
	}
	norm = path.Clean(decoded)
	if !artifactPathRegex.MatchString(norm) {
		return norm, "", "", false
	}
	ver = path.Base(norm)
	pkg = path.Dir(norm)
	return norm, pkg, ver, true
}

func isEligible(artifact Artifact, minRange CaretRange, hasValidRange bool) bool {
	if !hasValidRange {
		return false
	}
	_, _, verStr, ok := parseArtifactPath(artifact.RawPath)
	if !ok || !isValidChannel(artifact.Channel) {
		return false
	}
	ver, err := parseSemVer(verStr)
	if err != nil {
		return false
	}
	return minRange.Satisfies(ver)
}

func evaluate(input Input) Output {
	minRange, err := parseCaretRange(input.MinRange)
	hasValidRange := err == nil

	out := Output{
		Total: len(input.Artifacts),
	}

	for i, artifact := range input.Artifacts {
		out.TotalKB += artifact.SizeKB
		if i == 0 || artifact.SizeKB > out.MaxKB {
			out.MaxKB = artifact.SizeKB
		}
		if isEligible(artifact, minRange, hasValidRange) {
			out.Eligible++
		}
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

	enc := json.NewEncoder(os.Stdout)
	if err := enc.Encode(output); err != nil {
		fmt.Fprintf(os.Stderr, "failed to encode output JSON: %v\n", err)
		os.Exit(1)
	}
}
