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
	Count       int64 `json:"count"`
	Breaches    int64 `json:"breaches"`
	OverageMs   int64 `json:"overage_ms"`
	MaxMs       int64 `json:"max_ms"`
	MeanMs      int64 `json:"mean_ms"`
	BucketZero  int64 `json:"bucket_zero"`
	Critical            int64 `json:"critical"`
	WarnOrWorse         int64 `json:"warn_or_worse"`
	ConsecutiveBreaches int64 `json:"consecutive_breaches"`
	SpikeSteps          int64 `json:"spike_steps"`
}

func normalizeService(service string) string {
	return strings.ToLower(strings.TrimSpace(service))
}

func classifyLatency(ms int64) string {
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

func remEuclid(a, b int64) int64 {
	r := a % b
	if r < 0 {
		if b < 0 {
			r -= b
		} else {
			r += b
		}
	}
	return r
}

func audit(in Input) Output {
	slaMs := in.SlaS * 1000.0
	slaMsInt := int64(math.RoundToEven(slaMs))

	count := int64(len(in.Samples))
	if count == 0 {
		return Output{}
	}

	var breaches int64
	var overageMs int64
	var sumMs int64
	var bucketZero int64
	var critical int64
	var warnOrWorse int64
	var consecutiveBreaches int64
	var spikeSteps int64
	maxMs := in.Samples[0].Ms

	var prevBreach bool
	var prevMs int64

	for i, sample := range in.Samples {
		_ = normalizeService(sample.Service)

		if sample.Ms > maxMs {
			maxMs = sample.Ms
		}
		sumMs += sample.Ms

		isBreach := float64(sample.Ms) > slaMs
		if isBreach {
			breaches++
			overageMs += sample.Ms - slaMsInt
		}

		if i > 0 {
			if prevBreach && isBreach {
				consecutiveBreaches++
			}
			if sample.Ms > prevMs+100 {
				spikeSteps++
			}
		}
		prevBreach = isBreach
		prevMs = sample.Ms

		if remEuclid(sample.Offset, 4) == 0 {
			bucketZero++
		}

		severity := classifyLatency(sample.Ms)
		if severity == "critical" {
			critical++
		}
		if severity != "ok" {
			warnOrWorse++
		}
	}

	meanMs := int64(math.RoundToEven(float64(sumMs) / float64(count)))

	return Output{
		Count:               count,
		Breaches:            breaches,
		OverageMs:           overageMs,
		MaxMs:               maxMs,
		MeanMs:              meanMs,
		BucketZero:          bucketZero,
		Critical:            critical,
		WarnOrWorse:         warnOrWorse,
		ConsecutiveBreaches: consecutiveBreaches,
		SpikeSteps:          spikeSteps,
	}
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
