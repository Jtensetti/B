// Command main reads a warehouse snapshot as JSON on stdin and prints reorder suggestions.
package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"sort"
	"time"
	"unicode/utf16"

	"example.com/leadtime"
)

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

const isoLayout = "2006-01-02"

// mean mirrors libs/stats mean: 0 for an empty slice.
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

// trailingMean mirrors libs/stats trailing_mean: mean of the last window values
// (all values when there are fewer); 0 for empty.
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

// percentile mirrors libs/stats percentile: nearest rank on sorted values, 0 for empty.
func percentile(values []float64, p float64) float64 {
	if len(values) == 0 {
		return 0
	}
	v := append([]float64(nil), values...)
	sort.Float64s(v)
	rank := int(math.Max(math.Ceil((p/100.0)*float64(len(v))), 1))
	if rank > len(v) {
		rank = len(v)
	}
	return v[rank-1]
}

// roundUp mirrors libs/Packaging Packs.RoundUp.
func roundUp(quantity, packSize int) (int, error) {
	if packSize <= 0 {
		return 0, errors.New("pack size must be positive")
	}
	if quantity <= 0 {
		return 0, nil
	}
	return (quantity + packSize - 1) / packSize * packSize, nil
}

// addDays mirrors libs/weeks add_days.
func addDays(isoDate string, days int) (string, error) {
	d, err := time.Parse(isoLayout, isoDate)
	if err != nil {
		return "", err
	}
	return d.AddDate(0, 0, days).Format(isoLayout), nil
}

// distance mirrors fastest-levenshtein distance: unit-cost edit distance over UTF-16 code units.
func distance(a, b string) int {
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

// resolveSupplier matches a supplier name to the closest known supplier, within distance 2.
// Ties go to the alphabetically first name.
func resolveSupplier(name string) (string, bool) {
	known := append([]string(nil), leadtime.Suppliers()...)
	sort.Strings(known)
	best, bestD := "", -1
	for _, k := range known {
		d := distance(name, k)
		if bestD < 0 || d < bestD {
			best, bestD = k, d
		}
	}
	if bestD < 0 || bestD > 2 {
		return "", false
	}
	return best, true
}

// toWeekday mirrors libs/weeks to_weekday: the date itself on Monday to Friday,
// otherwise the following Monday.
func toWeekday(isoDate string) (string, error) {
	d, err := time.Parse(isoLayout, isoDate)
	if err != nil {
		return "", err
	}
	for d.Weekday() == time.Saturday || d.Weekday() == time.Sunday {
		d = d.AddDate(0, 0, 1)
	}
	return d.Format(isoLayout), nil
}

func run(r io.Reader, w io.Writer) error {
	var in input
	if err := json.NewDecoder(r).Decode(&in); err != nil {
		return err
	}
	today, err := time.Parse(isoLayout, in.Today)
	if err != nil {
		return err
	}
	start := today.AddDate(0, 0, -28)
	// Season: weeks 48 to 52 (iso_week of today) scale the forecast by 1.25.
	_, week := today.ISOWeek()
	seasonal := week >= 48 && week <= 52

	// Daily series per SKU: index 0 is today-28, index 27 is yesterday.
	series := map[string][]float64{}
	for _, s := range in.Sales {
		d, err := time.Parse(isoLayout, s.Date)
		if err != nil {
			continue
		}
		idx := int(d.Sub(start).Hours() / 24)
		if idx < 0 || idx >= 28 {
			continue
		}
		if series[s.SKU] == nil {
			series[s.SKU] = make([]float64, 28)
		}
		series[s.SKU][idx] += float64(s.Qty)
	}

	out := output{Orders: map[string]order{}, Unknown: []string{}}
	for _, it := range in.Items {
		supplier, ok := resolveSupplier(it.Supplier)
		if !ok {
			out.Unknown = append(out.Unknown, it.SKU)
			continue
		}
		lead, err := leadtime.Days(supplier)
		if err != nil {
			out.Unknown = append(out.Unknown, it.SKU)
			continue
		}
		ser := series[it.SKU]
		if ser == nil {
			ser = make([]float64, 28)
		}
		forecast := trailingMean(ser, 7)
		if seasonal {
			forecast *= 1.25
		}
		safety := percentile(ser, 90)
		need := forecast*float64(lead+7) + safety - float64(it.Stock)
		if need <= 0 {
			continue
		}
		qty, err := roundUp(int(math.Ceil(need)), it.Pack)
		if err != nil {
			return fmt.Errorf("sku %s: %w", it.SKU, err)
		}
		if float64(qty)*it.Price < 500 {
			continue
		}
		due, err := addDays(in.Today, lead)
		if err != nil {
			return err
		}
		arrive, err := toWeekday(due)
		if err != nil {
			return err
		}
		out.Orders[it.SKU] = order{Qty: qty, Arrive: arrive}
	}
	sort.Strings(out.Unknown)

	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	return enc.Encode(out)
}

func main() {
	if err := run(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "error:", err)
		os.Exit(1)
	}
}
