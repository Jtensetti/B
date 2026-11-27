package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"strings"
	"unicode/utf8"
)

type Sample struct {
	Service string `json:"service"`
	Ms      int64  `json:"ms"`
	Offset  int64  `json:"offset"`
}

type Input struct {
	SlaS    float64  `json:"sla_s"`
	Samples []Sample `json:"samples"`
}

type Output struct {
	Count               int    `json:"count"`
	Breaches            int    `json:"breaches"`
	OverageMs           int64  `json:"overage_ms"`
	MaxMs               int64  `json:"max_ms"`
	MeanMs              int64  `json:"mean_ms"`
	BucketZero          int    `json:"bucket_zero"`
	Critical            int    `json:"critical"`
	WarnOrWorse         int    `json:"warn_or_worse"`
	ConsecutiveBreaches int    `json:"consecutive_breaches"`
	SpikeSteps          int    `json:"spike_steps"`
	InvalidLabels       int    `json:"invalid_labels"`
	Exempt              int    `json:"exempt"`
	Regressed           int    `json:"regressed"`
	Status              string `json:"status"`
}

type normalizedSample struct {
	service string
	ms      int64
	offset  int64
}

func normalizeService(name string) string {
	return strings.ToLower(strings.TrimSpace(name))
}

func isValidServiceLabel(service string) bool {
	n := utf8.RuneCountInString(service)
	return n >= 2 && n <= 12
}

func classifySeverity(ms int64) string {
	switch {
	case ms < 200:
		return "ok"
	case ms <= 500:
		return "warn"
	case ms <= 1000:
		return "slow"
	default:
		return "critical"
	}
}

func computeStatus(out Output) string {
	switch {
	case out.ConsecutiveBreaches >= 2 || out.Critical > 0:
		return "red"
	case out.Breaches > 0 || out.InvalidLabels > 0:
		return "yellow"
	default:
		return "green"
	}
}

func remEuclid(a, m int64) int64 {
	r := a % m
	if r < 0 {
		if m < 0 {
			r -= m
		} else {
			r += m
		}
	}
	return r
}

func roundHalfToEven(v float64) int64 {
	return int64(math.RoundToEven(v))
}

func audit(in Input) Output {
	slaMs := in.SlaS * 1000.0
	slaMsInt := roundHalfToEven(slaMs)

	samples := make([]normalizedSample, len(in.Samples))
	for i, s := range in.Samples {
		samples[i] = normalizedSample{
			service: normalizeService(s.Service),
			ms:      s.Ms,
			offset:  s.Offset,
		}
	}

	out := Output{
		Count: len(samples),
	}
	if len(samples) == 0 {
		out.Status = computeStatus(out)
		return out
	}

	var validSumMs int64
	var validCount int
	out.MaxMs = samples[0].ms
	minMs := samples[0].ms
	var prevBreach bool
	var prevMs int64
	for i, s := range samples {
		if isValidServiceLabel(s.service) {
			validSumMs += s.ms
			validCount++
		} else {
			out.InvalidLabels++
		}
		if s.ms > out.MaxMs {
			out.MaxMs = s.ms
		}
		bucketZero := remEuclid(s.offset, 4) == 0
		if bucketZero {
			out.BucketZero++
		}
		rawBreach := float64(s.ms) > slaMs
		exempt := s.service == "healthcheck" && bucketZero
		breach := rawBreach && !exempt
		if rawBreach && exempt {
			out.Exempt++
		}
		if breach {
			out.Breaches++
			out.OverageMs += s.ms - slaMsInt
		}
		severity := classifySeverity(s.ms)
		if severity == "critical" {
			out.Critical++
		}
		if severity != "ok" {
			out.WarnOrWorse++
		}
		if i > 0 {
			if prevBreach && breach {
				out.ConsecutiveBreaches++
			}
			if s.ms > prevMs+100 {
				out.SpikeSteps++
			}
			if minMs+300 < s.ms {
				out.Regressed++
			}
			if s.ms < minMs {
				minMs = s.ms
			}
		}
		prevBreach = breach
		prevMs = s.ms
	}

	if validCount > 0 {
		out.MeanMs = roundHalfToEven(float64(validSumMs) / float64(validCount))
	}
	out.Status = computeStatus(out)
	return out
}

func main() {
	var in Input
	if err := json.NewDecoder(os.Stdin).Decode(&in); err != nil {
		fmt.Fprintf(os.Stderr, "failed to decode input JSON: %v\n", err)
		os.Exit(1)
	}

	out := audit(in)

	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(out); err != nil {
		fmt.Fprintf(os.Stderr, "failed to encode output JSON: %v\n", err)
		os.Exit(1)
	}
}
