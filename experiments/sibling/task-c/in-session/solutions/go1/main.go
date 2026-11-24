// Command main reads a warehouse snapshot as JSON on standard input and
// prints reorder suggestions as one line of JSON on standard output.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"sort"
	"time"
	"unicode/utf16"

	"example.com/leadtime"
)

const isoLayout = "2006-01-02"

// minOrderValue is the smallest order value in SEK that is placed.
const minOrderValue = 500

// window is the number of days in an item's daily series.
const window = 28

type item struct {
	SKU      string  `json:"sku"`
	Supplier string  `json:"supplier"`
	Stock    int     `json:"stock"`
	Pack     int     `json:"pack"`
	Price    float64 `json:"price"`
}

type sale struct {
	SKU  string `json:"sku"`
	Date string `json:"date"`
	Qty  int    `json:"qty"`
}

type input struct {
	Today string `json:"today"`
	Items []item `json:"items"`
	Sales []sale `json:"sales"`
}

type order struct {
	Qty    int    `json:"qty"`
	Arrive string `json:"arrive"`
}

type output struct {
	Orders  map[string]order `json:"orders"`
	Unknown []string         `json:"unknown"`
}

func main() {
	if err := run(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}

func run(r *os.File, w *os.File) error {
	var in input
	if err := json.NewDecoder(r).Decode(&in); err != nil {
		return fmt.Errorf("reading input: %w", err)
	}
	today, err := time.Parse(isoLayout, in.Today)
	if err != nil {
		return fmt.Errorf("today: %w", err)
	}

	series := dailySeries(today, in.Sales)
	_, week := today.ISOWeek()
	peak := week >= 48 && week <= 52

	out := output{Orders: map[string]order{}, Unknown: []string{}}
	for _, it := range in.Items {
		lead, err := leadtime.Days(it.Supplier)
		if err != nil {
			name, ok := closestSupplier(it.Supplier)
			if !ok {
				out.Unknown = append(out.Unknown, it.SKU)
				continue
			}
			lead, err = leadtime.Days(name)
			if err != nil {
				out.Unknown = append(out.Unknown, it.SKU)
				continue
			}
		}
		s := series[it.SKU]
		forecast := trailingMean(s, 7)
		if peak {
			forecast *= 1.25
		}
		safety := percentile(s, 90)
		need := float64(forecast*float64(lead+7)) + safety - float64(it.Stock)
		if need <= 0 {
			continue
		}
		qty, err := roundUp(int(math.Ceil(need)), it.Pack)
		if err != nil {
			return fmt.Errorf("sku %q: %w", it.SKU, err)
		}
		if float64(qty)*it.Price < minOrderValue {
			continue
		}
		out.Orders[it.SKU] = order{
			Qty:    qty,
			Arrive: toWeekday(today.AddDate(0, 0, lead)).Format(isoLayout),
		}
	}
	sort.Strings(out.Unknown)

	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	return enc.Encode(out)
}

// dailySeries returns, per sku, the quantity sold on each of the 28 days
// before today, oldest first. Sales outside that window are ignored.
func dailySeries(today time.Time, sales []sale) map[string][]float64 {
	series := map[string][]float64{}
	for _, s := range sales {
		d, err := time.Parse(isoLayout, s.Date)
		if err != nil {
			continue
		}
		offset := int((d.Unix() - today.Unix()) / 86400)
		if offset < -window || offset > -1 {
			continue
		}
		v, ok := series[s.SKU]
		if !ok {
			v = make([]float64, window)
			series[s.SKU] = v
		}
		v[offset+window] += float64(s.Qty)
	}
	return series
}

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

// trailingMean is the mean of the last window values (all values when there
// are fewer); 0 for an empty slice.
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

// percentile is the nearest-rank percentile (p in 0..100); 0 for an empty slice.
func percentile(values []float64, p float64) float64 {
	n := len(values)
	if n == 0 {
		return 0
	}
	v := append([]float64(nil), values...)
	sort.Float64s(v)
	rank := int(math.Max(math.Ceil((p/100.0)*float64(n)), 1))
	if rank > n {
		rank = n
	}
	return v[rank-1]
}

// closestSupplier returns the known supplier nearest to name by Levenshtein
// distance, if that distance is at most 2. Ties go to the alphabetically first.
func closestSupplier(name string) (string, bool) {
	names := leadtime.Suppliers()
	sort.Strings(names)
	best, bestDist := "", 3
	for _, n := range names {
		if d := levenshtein(name, n); d < bestDist {
			best, bestDist = n, d
		}
	}
	return best, bestDist <= 2
}

// levenshtein is the edit distance between a and b, counted in UTF-16 code units.
func levenshtein(a, b string) int {
	x := utf16.Encode([]rune(a))
	y := utf16.Encode([]rune(b))
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
			cur[j] = min(prev[j]+1, cur[j-1]+1, prev[j-1]+cost)
		}
		prev, cur = cur, prev
	}
	return prev[len(y)]
}

// toWeekday returns the date itself on Monday to Friday, and the following
// Monday for a Saturday or Sunday.
func toWeekday(d time.Time) time.Time {
	for d.Weekday() == time.Saturday || d.Weekday() == time.Sunday {
		d = d.AddDate(0, 0, 1)
	}
	return d
}

// roundUp returns the smallest multiple of pack that is at least quantity.
// Quantities of 0 or less give 0.
func roundUp(quantity, pack int) (int, error) {
	if pack <= 0 {
		return 0, errors.New("pack size must be positive")
	}
	if quantity <= 0 {
		return 0, nil
	}
	return (quantity + pack - 1) / pack * pack, nil
}
