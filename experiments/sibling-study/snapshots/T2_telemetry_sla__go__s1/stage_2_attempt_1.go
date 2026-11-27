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
	MS      int64  `json:"ms"`
	Offset  int64  `json:"offset"`
}

type Input struct {
	SLASeconds float64  `json:"sla_s"`
	Samples    []Sample `json:"samples"`
}

type Output struct {
	Count               int64 `json:"count"`
	Breaches            int64 `json:"breaches"`
	OverageMS           int64 `json:"overage_ms"`
	MaxMS               int64 `json:"max_ms"`
	MeanMS              int64 `json:"mean_ms"`
	BucketZero          int64 `json:"bucket_zero"`
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

func roundHalfToEven(v float64) int64 {
	return int64(math.RoundToEven(v))
}

func audit(in Input) Output {
	slaMS := in.SLASeconds * 1000.0
	slaMSInt := roundHalfToEven(slaMS)

	count := int64(len(in.Samples))
	if count == 0 {
		return Output{}
	}

	var breaches int64
	var overageMS int64
	var sumMS int64
	var bucketZero int64
	var critical int64
	var warnOrWorse int64
	var consecutiveBreaches int64
	var spikeSteps int64
	maxMS := in.Samples[0].MS

	prevBreach := false
	for i, sample := range in.Samples {
		_ = normalizeService(sample.Service)

		isBreach := float64(sample.MS) > slaMS
		if isBreach {
			breaches++
			overageMS += sample.MS - slaMSInt
		}
		if sample.MS > maxMS {
			maxMS = sample.MS
		}
		sumMS += sample.MS
		if remEuclid(sample.Offset, 4) == 0 {
			bucketZero++
		}

		severity := classifyLatency(sample.MS)
		if severity == "critical" {
			critical++
		}
		if severity != "ok" {
			warnOrWorse++
		}

		if i > 0 {
			if prevBreach && isBreach {
				consecutiveBreaches++
			}
			if sample.MS > in.Samples[i-1].MS+100 {
				spikeSteps++
			}
		}
		prevBreach = isBreach
	}

	meanMS := roundHalfToEven(float64(sumMS) / float64(count))

	return Output{
		Count:               count,
		Breaches:            breaches,
		OverageMS:           overageMS,
		MaxMS:               maxMS,
		MeanMS:              meanMS,
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
		fmt.Fprintf(os.Stderr, "failed to decode input: %v\n", err)
		os.Exit(1)
	}

	out := audit(in)

	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(out); err != nil {
		fmt.Fprintf(os.Stderr, "failed to encode output: %v\n", err)
		os.Exit(1)
	}
}
