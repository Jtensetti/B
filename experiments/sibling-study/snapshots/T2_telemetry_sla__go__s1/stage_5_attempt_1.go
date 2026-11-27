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
	InvalidLabels       int64  `json:"invalid_labels"`
	Exempt              int64  `json:"exempt"`
	Regressed           int64  `json:"regressed"`
	Status              string `json:"status"`
}

func normalizeService(service string) string {
	return strings.ToLower(strings.TrimSpace(service))
}

func isValidServiceLabel(normalized string) bool {
	n := utf8.RuneCountInString(normalized)
	return n >= 2 && n <= 12
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

func overallStatus(consecutiveBreaches, critical, breaches, invalidLabels int64) string {
	switch {
	case consecutiveBreaches >= 2 || critical > 0:
		return "red"
	case breaches > 0 || invalidLabels > 0:
		return "yellow"
	default:
		return "green"
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
		return Output{
			Status: "green",
		}
	}

	var breaches int64
	var overageMS int64
	var validSumMS int64
	var validCount int64
	var invalidLabels int64
	var bucketZero int64
	var critical int64
	var warnOrWorse int64
	var consecutiveBreaches int64
	var spikeSteps int64
	var exempt int64
	var regressed int64
	maxMS := in.Samples[0].MS
	minEarlierMS := in.Samples[0].MS

	prevBreach := false
	for i, sample := range in.Samples {
		normalized := normalizeService(sample.Service)
		if isValidServiceLabel(normalized) {
			validCount++
			validSumMS += sample.MS
		} else {
			invalidLabels++
		}

		inBucketZero := remEuclid(sample.Offset, 4) == 0
		if inBucketZero {
			bucketZero++
		}

		rawBreach := float64(sample.MS) > slaMS
		isExempt := rawBreach && normalized == "healthcheck" && inBucketZero
		if isExempt {
			exempt++
		}
		isBreach := rawBreach && !isExempt
		if isBreach {
			breaches++
			overageMS += sample.MS - slaMSInt
		}
		if sample.MS > maxMS {
			maxMS = sample.MS
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
			if minEarlierMS+300 < sample.MS {
				regressed++
			}
			if sample.MS < minEarlierMS {
				minEarlierMS = sample.MS
			}
		}
		prevBreach = isBreach
	}

	var meanMS int64
	if validCount > 0 {
		meanMS = roundHalfToEven(float64(validSumMS) / float64(validCount))
	}

	status := overallStatus(consecutiveBreaches, critical, breaches, invalidLabels)

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
		InvalidLabels:       invalidLabels,
		Exempt:              exempt,
		Regressed:           regressed,
		Status:              status,
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
