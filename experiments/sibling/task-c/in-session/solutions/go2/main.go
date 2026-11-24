// Command warehouse suggests reorders for a furniture warehouse from stock and 28 days of sales.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"sort"
	"time"

	"example.com/leadtime"
)

const (
	window              = 28
	maxSupplierDistance = 2
	minOrderValue       = 500.0
)

// sortedSuppliers is the list of known supplier names in alphabetical order, so ties go to the first name.
func sortedSuppliers() []string {
	names := append([]string(nil), leadtime.Suppliers()...)
	sort.Strings(names)
	return names
}

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

func run(r io.Reader, w io.Writer) error {
	var in input
	if err := json.NewDecoder(r).Decode(&in); err != nil {
		return fmt.Errorf("reading input: %w", err)
	}
	out, err := reorder(in)
	if err != nil {
		return err
	}
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	return enc.Encode(out)
}

func reorder(in input) (output, error) {
	today, err := time.Parse(isoLayout, in.Today)
	if err != nil {
		return output{}, fmt.Errorf("today: %w", err)
	}
	start := today.AddDate(0, 0, -window)
	day := 24 * time.Hour

	// Daily quantities per SKU for the 28 days before today, oldest first.
	series := make(map[string]*[window]float64)
	for _, it := range in.Items {
		if _, ok := series[it.SKU]; !ok {
			series[it.SKU] = new([window]float64)
		}
	}
	for _, s := range in.Sales {
		d, err := time.Parse(isoLayout, s.Date)
		if err != nil {
			return output{}, fmt.Errorf("sale date for %q: %w", s.SKU, err)
		}
		daily, ok := series[s.SKU]
		if !ok {
			continue
		}
		diff := d.Sub(start)
		if diff < 0 || diff >= window*day {
			continue
		}
		daily[int(diff/day)] += float64(s.Qty)
	}

	week, err := isoWeek(in.Today)
	if err != nil {
		return output{}, fmt.Errorf("today: %w", err)
	}
	peak := week >= 48 && week <= 52

	out := output{Orders: map[string]order{}, Unknown: []string{}}
	for _, it := range in.Items {
		supplier, dist := closest(it.Supplier, sortedSuppliers())
		if dist > maxSupplierDistance {
			out.Unknown = append(out.Unknown, it.SKU)
			continue
		}
		lead, err := leadtime.Days(supplier)
		if err != nil {
			out.Unknown = append(out.Unknown, it.SKU)
			continue
		}
		s := series[it.SKU][:]
		forecast := trailingMean(s, 7)
		if peak {
			forecast = forecast * 1.25
		}
		safety := percentile(s, 90)
		// Separate statements keep the float operations unfused and in the reference order.
		t := forecast * float64(lead+7)
		t = t + safety
		need := t - float64(it.Stock)
		if need <= 0 {
			continue
		}
		qty, err := roundUp(int(math.Ceil(need)), it.Pack)
		if err != nil {
			return output{}, fmt.Errorf("sku %q: %w", it.SKU, err)
		}
		arrive, err := addDays(in.Today, lead)
		if err != nil {
			return output{}, err
		}
		arrive, err = toWeekday(arrive)
		if err != nil {
			return output{}, err
		}
		if float64(qty)*it.Price < minOrderValue {
			continue
		}
		out.Orders[it.SKU] = order{Qty: qty, Arrive: arrive}
	}
	sort.Strings(out.Unknown)
	if len(out.Unknown) == 0 {
		out.Unknown = []string{}
	}
	return out, nil
}
