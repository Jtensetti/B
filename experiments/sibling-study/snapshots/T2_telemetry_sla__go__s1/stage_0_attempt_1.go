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
	Count      int64 `json:"count"`
	Breaches   int64 `json:"breaches"`
	OverageMS  int64 `json:"overage_ms"`
	MaxMS      int64 `json:"max_ms"`
	MeanMS     int64 `json:"mean_ms"`
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
	maxMS := in.Samples[0].MS

	for _, sample := range in.Samples {
		_ = normalizeService(sample.Service)

		if float64(sample.MS) > slaMS {
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
	}

	meanMS := roundHalfToEven(float64(sumMS) / float64(count))

	return Output{
		Count:      count,
		Breaches:   breaches,
		OverageMS:  overageMS,
		MaxMS:      maxMS,
		MeanMS:     meanMS,
		BucketZero: bucketZero,
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
