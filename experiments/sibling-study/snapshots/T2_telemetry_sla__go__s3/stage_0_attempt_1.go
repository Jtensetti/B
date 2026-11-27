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
	Count      int64 `json:"count"`
	Breaches   int64 `json:"breaches"`
	OverageMs  int64 `json:"overage_ms"`
	MaxMs      int64 `json:"max_ms"`
	MeanMs     int64 `json:"mean_ms"`
	BucketZero int64 `json:"bucket_zero"`
}

func normalizeService(service string) string {
	return strings.ToLower(strings.TrimSpace(service))
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
	maxMs := in.Samples[0].Ms

	for _, sample := range in.Samples {
		_ = normalizeService(sample.Service)

		if sample.Ms > maxMs {
			maxMs = sample.Ms
		}
		sumMs += sample.Ms

		if float64(sample.Ms) > slaMs {
			breaches++
			overageMs += sample.Ms - slaMsInt
		}

		if remEuclid(sample.Offset, 4) == 0 {
			bucketZero++
		}
	}

	meanMs := int64(math.RoundToEven(float64(sumMs) / float64(count)))

	return Output{
		Count:      count,
		Breaches:   breaches,
		OverageMs:  overageMs,
		MaxMs:      maxMs,
		MeanMs:     meanMs,
		BucketZero: bucketZero,
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
