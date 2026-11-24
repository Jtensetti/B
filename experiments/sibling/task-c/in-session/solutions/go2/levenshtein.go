package main

// Port of node_modules/fastest-levenshtein (JS): distance and closest, over UTF-16 code units.

import (
	"math"
	"unicode/utf16"
)

// levenshtein is the edit distance between a and b.
func levenshtein(a, b string) int {
	x := utf16.Encode([]rune(a))
	y := utf16.Encode([]rune(b))
	if len(x) < len(y) {
		x, y = y, x
	}
	if len(y) == 0 {
		return len(x)
	}
	prev := make([]int, len(y)+1)
	cur := make([]int, len(y)+1)
	for j := range prev {
		prev[j] = j
	}
	for i := 1; i <= len(x); i++ {
		cur[0] = i
		for j := 1; j <= len(y); j++ {
			cost := 1
			if x[i-1] == y[j-1] {
				cost = 0
			}
			cur[j] = minInt(prev[j]+1, cur[j-1]+1, prev[j-1]+cost)
		}
		prev, cur = cur, prev
	}
	return prev[len(y)]
}

// closest returns the entry of names with the smallest distance to name (first one wins ties) and that distance.
func closest(name string, names []string) (string, int) {
	best := ""
	bestDist := math.MaxInt
	for _, n := range names {
		if d := levenshtein(name, n); d < bestDist {
			best, bestDist = n, d
		}
	}
	return best, bestDist
}

func minInt(vs ...int) int {
	m := vs[0]
	for _, v := range vs[1:] {
		if v < m {
			m = v
		}
	}
	return m
}
