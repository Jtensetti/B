// Command delivery reads one JSON order batch on stdin and writes delivery quotes as one JSON line.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"sort"
	"strings"
	"time"
	"unicode/utf16"

	"example.com/tariff"
)

type Point struct {
	Lat float64 `json:"lat"`
	Lon float64 `json:"lon"`
}

type Order struct {
	ID       string   `json:"id"`
	Product  string   `json:"product"`
	Country  string   `json:"country"`
	Lat      float64  `json:"lat"`
	Lon      float64  `json:"lon"`
	Date     string   `json:"date"`
	Business bool     `json:"business"`
	Qty      *float64 `json:"qty,omitempty"`
	Express  bool     `json:"express,omitempty"`
}

type Input struct {
	Depot   Point              `json:"depot"`
	Catalog map[string]float64 `json:"catalog"`
	Orders  []Order            `json:"orders"`
	Rates   map[string]float64 `json:"rates,omitempty"`
}

type Quote struct {
	Price    float64 `json:"price"`
	Delivery string  `json:"delivery"`
	Currency string  `json:"currency"`
}

type Output struct {
	Quotes  map[string]Quote `json:"quotes"`
	Unknown []string         `json:"unknown"`
}

// freeFreightKg is the parcel weight from which business orders pay no BasePrice.
const freeFreightKg = 50.0

// maxDistanceSurcharge caps the distance surcharge per order, in SEK.
const maxDistanceSurcharge = 400.0

// maxProductDistance is the largest Levenshtein distance at which a product name still matches.
const maxProductDistance = 2

// ---- Product matching (port of node_modules/fastest-levenshtein) ----

// levenshtein is the edit distance over UTF-16 code units, as the JS library computes it.
func levenshtein(a, b string) int {
	x := utf16.Encode([]rune(a))
	y := utf16.Encode([]rune(b))
	if len(x) == 0 {
		return len(y)
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
			cur[j] = min(prev[j]+1, cur[j-1]+1, prev[j-1]+cost)
		}
		prev, cur = cur, prev
	}
	return prev[len(y)]
}

// matchProduct returns the catalog name with the smallest distance to name (ties go to the
// alphabetically first name), provided that distance is at most maxProductDistance.
func matchProduct(name string, catalog map[string]float64) (string, bool) {
	best := ""
	bestD := -1
	for k := range catalog {
		d := levenshtein(name, k)
		if bestD < 0 || d < bestD || (d == bestD && k < best) {
			best, bestD = k, d
		}
	}
	if bestD < 0 || bestD > maxProductDistance {
		return "", false
	}
	return best, true
}

// ---- Geo (port of libs/geo, Rust) ----

const earthRadiusKm = 6371.0

func toRadians(deg float64) float64 { return deg * (math.Pi / 180.0) }

func distanceKm(lat1, lon1, lat2, lon2 float64) float64 {
	p1, p2 := toRadians(lat1), toRadians(lat2)
	dp := toRadians(lat2 - lat1)
	dl := toRadians(lon2 - lon1)
	s1 := math.Sin(dp / 2.0)
	s2 := math.Sin(dl / 2.0)
	a := s1*s1 + math.Cos(p1)*math.Cos(p2)*s2*s2
	return 2.0 * earthRadiusKm * math.Asin(math.Sqrt(a))
}

// roadKm is the routing team's estimate: great-circle distance times 1.25.
func roadKm(lat1, lon1, lat2, lon2 float64) float64 {
	return distanceKm(lat1, lon1, lat2, lon2) * 1.25
}

// ---- VAT (port of libs/Tax/Vat.cs, C#) ----

var vatStandard = map[string]float64{
	"SE": 0.25, "NO": 0.25, "DK": 0.25, "FI": 0.255, "DE": 0.19,
	"NL": 0.21, "PL": 0.23, "FR": 0.20, "ES": 0.21, "IT": 0.22,
}

var vatEU = map[string]bool{
	"SE": true, "DK": true, "FI": true, "DE": true, "NL": true,
	"PL": true, "FR": true, "ES": true, "IT": true,
}

func normCountry(c string) string {
	return strings.ToUpper(strings.TrimSpace(c))
}

// vatRate returns the standard VAT rate for a country and whether the country is known.
func vatRate(country string) (float64, bool) {
	r, ok := vatStandard[normCountry(country)]
	return r, ok
}

// reverseCharge is true when a business customer in another EU country pays no VAT.
func reverseCharge(country string, business bool) bool {
	c := normCountry(country)
	return business && c != "SE" && vatEU[c]
}

// ---- Working days (port of libs/calendar/workdays.py, Python) ----

var holidays2026 = map[string]bool{
	"2026-01-01": true, "2026-01-06": true, "2026-04-03": true, "2026-04-06": true,
	"2026-05-01": true, "2026-05-14": true, "2026-06-06": true, "2026-06-19": true,
	"2026-12-24": true, "2026-12-25": true, "2026-12-26": true, "2026-12-31": true,
}

const isoLayout = "2006-01-02"

func isWorkday(d time.Time) bool {
	wd := d.Weekday()
	return wd != time.Saturday && wd != time.Sunday && !holidays2026[d.Format(isoLayout)]
}

// nextWorkday returns the first working day strictly after the given ISO date.
func nextWorkday(iso string) (string, error) {
	d, err := time.Parse(isoLayout, iso)
	if err != nil {
		return "", err
	}
	d = d.AddDate(0, 0, 1)
	for !isWorkday(d) {
		d = d.AddDate(0, 0, 1)
	}
	return d.Format(isoLayout), nil
}

// deliveryDate is the order date itself for express orders on a working day, otherwise the next working day.
func deliveryDate(o Order) (string, error) {
	if o.Express {
		d, err := time.Parse(isoLayout, o.Date)
		if err != nil {
			return "", err
		}
		if isWorkday(d) {
			return o.Date, nil
		}
	}
	return nextWorkday(o.Date)
}

// ---- Quoting ----

// quote computes the price and delivery date for one order. ok is false when the order is unknown.
func quote(in Input, o Order) (Quote, bool) {
	product, ok := matchProduct(o.Product, in.Catalog)
	if !ok {
		return Quote{}, false
	}
	zone, err := tariff.Zone(o.Country)
	if err != nil {
		return Quote{}, false
	}
	delivery, err := deliveryDate(o)
	if err != nil {
		return Quote{}, false
	}
	qty := 1.0
	if o.Qty != nil {
		qty = *o.Qty
	}
	weight := qty * in.Catalog[product]
	base := tariff.BasePrice(zone, weight)
	if o.Business && weight >= freeFreightKg {
		base = 0
	}

	road := roadKm(in.Depot.Lat, in.Depot.Lon, o.Lat, o.Lon)
	if o.Express {
		base *= 1.5
	}
	surcharge := math.Min(0.80*math.Max(0, road-300), maxDistanceSurcharge)
	net := base + surcharge

	var rate float64
	if !reverseCharge(o.Country, o.Business) {
		r, known := vatRate(o.Country)
		if !known {
			return Quote{}, false
		}
		rate = r
	}
	price := net * (1 + rate)
	price = math.Round(price*100) / 100

	if normCountry(o.Country) == "SE" {
		return Quote{Price: price, Delivery: delivery, Currency: "SEK"}, true
	}
	eur, ok := in.Rates["EUR"]
	if !ok || eur <= 0 {
		return Quote{}, false
	}
	return Quote{Price: math.Round(price/eur*100) / 100, Delivery: delivery, Currency: "EUR"}, true
}

func run(r io.Reader, w io.Writer) error {
	var in Input
	if err := json.NewDecoder(r).Decode(&in); err != nil {
		return fmt.Errorf("decode input: %w", err)
	}
	out := Output{Quotes: map[string]Quote{}, Unknown: []string{}}
	for _, o := range in.Orders {
		if q, ok := quote(in, o); ok {
			out.Quotes[o.ID] = q
		} else {
			out.Unknown = append(out.Unknown, o.ID)
		}
	}
	sort.Strings(out.Unknown)
	return json.NewEncoder(w).Encode(out)
}

func main() {
	if err := run(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
