package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"strings"
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
	Count               int   `json:"count"`
	Breaches            int   `json:"breaches"`
	OverageMs           int64 `json:"overage_ms"`
	MaxMs               int64 `json:"max_ms"`
	MeanMs              int64 `json:"mean_ms"`
	BucketZero          int   `json:"bucket_zero"`
	Critical            int   `json:"critical"`
	WarnOrWorse         int   `json:"warn_or_worse"`
	ConsecutiveBreaches int   `json:"consecutive_breaches"`
	SpikeSteps          int   `json:"spike_steps"`
}

type normalizedSample struct {
	service string
	ms      int64
	offset  int64
}

func normalizeService(name string) string {
	return strings.ToLower(strings.TrimSpace(name))
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
		return out
	}

	var sumMs int64
	out.MaxMs = samples[0].ms
	var prevBreach bool
	var prevMs int64
	for i, s := range samples {
		_ = s.service
		sumMs += s.ms
		if s.ms > out.MaxMs {
			out.MaxMs = s.ms
		}
		breach := float64(s.ms) > slaMs
		if breach {
			out.Breaches++
			out.OverageMs += s.ms - slaMsInt
		}
		if remEuclid(s.offset, 4) == 0 {
			out.BucketZero++
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
		}
		prevBreach = breach
		prevMs = s.ms
	}

	out.MeanMs = roundHalfToEven(float64(sumMs) / float64(len(samples)))
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
