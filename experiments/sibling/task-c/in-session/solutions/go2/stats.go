package main

// Port of libs/stats (Rust): mean and percentile, same arithmetic and ordering.

import (
	"math"
	"sort"
)

// mean is the arithmetic mean; 0 for an empty slice.
func mean(values []float64) float64 {
	if len(values) == 0 {
		return 0
	}
	sum := 0.0
	for _, v := range values {
		sum += v
	}
	return sum / float64(len(values))
}

// percentile is the nearest-rank percentile of the sorted values (p in 0..100); 0 for an empty slice.
func percentile(values []float64, p float64) float64 {
	if len(values) == 0 {
		return 0
	}
	v := append([]float64(nil), values...)
	sort.Float64s(v)
	rank := int(math.Ceil((p / 100.0) * float64(len(v))))
	if rank < 1 {
		rank = 1
	}
	if rank > len(v) {
		rank = len(v)
	}
	return v[rank-1]
}

// trailingMean is the mean of the last window values (all values when there are fewer); 0 for an empty slice.
func trailingMean(values []float64, window int) float64 {
	n := len(values)
	w := window
	if w < 1 {
		w = 1
	}
	if w > n {
		w = n
	}
	if n == 0 {
		return 0
	}
	return mean(values[n-w:])
}
