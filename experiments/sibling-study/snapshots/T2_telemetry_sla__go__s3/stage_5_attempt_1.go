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
	InvalidLabels       int64  `json:"invalid_labels"`
	Exempt              int64  `json:"exempt"`
	Regressed           int64  `json:"regressed"`
	Status              string `json:"status"`
}

func normalizeService(service string) string {
	return strings.ToLower(strings.TrimSpace(service))
}

func isValidService(normalized string) bool {
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

func determineStatus(consecutiveBreaches, critical, breaches, invalidLabels int64) string {
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

func audit(in Input) Output {
	slaMs := in.SlaS * 1000.0
	slaMsInt := int64(math.RoundToEven(slaMs))

	count := int64(len(in.Samples))
	if count == 0 {
		return Output{
			Status: determineStatus(0, 0, 0, 0),
		}
	}

	var breaches int64
	var overageMs int64
	var validSumMs int64
	var validCount int64
	var invalidLabels int64
	var bucketZero int64
	var critical int64
	var warnOrWorse int64
	var consecutiveBreaches int64
	var spikeSteps int64
	var exempt int64
	var regressed int64
	maxMs := in.Samples[0].Ms
	minEarlierMs := in.Samples[0].Ms

	var prevBreach bool
	var prevMs int64

	for i, sample := range in.Samples {
		normalized := normalizeService(sample.Service)
		if isValidService(normalized) {
			validSumMs += sample.Ms
			validCount++
		} else {
			invalidLabels++
		}

		if sample.Ms > maxMs {
			maxMs = sample.Ms
		}

		inBucketZero := remEuclid(sample.Offset, 4) == 0
		if inBucketZero {
			bucketZero++
		}

		rawBreach := float64(sample.Ms) > slaMs
		isExempt := normalized == "healthcheck" && inBucketZero
		isBreach := rawBreach && !isExempt
		if rawBreach && isExempt {
			exempt++
		}
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
			if minEarlierMs+300 < sample.Ms {
				regressed++
			}
			if sample.Ms < minEarlierMs {
				minEarlierMs = sample.Ms
			}
		}
		prevBreach = isBreach
		prevMs = sample.Ms

		severity := classifyLatency(sample.Ms)
		if severity == "critical" {
			critical++
		}
		if severity != "ok" {
			warnOrWorse++
		}
	}

	var meanMs int64
	if validCount > 0 {
		meanMs = int64(math.RoundToEven(float64(validSumMs) / float64(validCount)))
	}

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
		InvalidLabels:       invalidLabels,
		Exempt:              exempt,
		Regressed:           regressed,
		Status:              determineStatus(consecutiveBreaches, critical, breaches, invalidLabels),
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
