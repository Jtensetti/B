// Command delivery reads one JSON request from stdin and writes one JSON quote
// document to stdout.
//
// The tariff comes from libs/tariff (Go). The VAT rules, road distance and
// Swedish working days are ported from libs/Tax (C#), libs/geo (Rust) and
// libs/calendar (Python), and the Levenshtein distance from the npm package
// fastest-levenshtein. The ports follow the library code operation by operation.
package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf16"

	"example.com/tariff"
)

type point struct {
	Lat float64 `json:"lat"`
	Lon float64 `json:"lon"`
}

type order struct {
	ID       string   `json:"id"`
	Product  string   `json:"product"`
	Country  string   `json:"country"`
	Lat      float64  `json:"lat"`
	Lon      float64  `json:"lon"`
	Date     string   `json:"date"`
	Business bool     `json:"business"`
	Qty      *float64 `json:"qty"`
	Express  bool     `json:"express"`
}

type request struct {
	Depot   point              `json:"depot"`
	Catalog map[string]float64 `json:"catalog"`
	Rates   map[string]float64 `json:"rates"`
	Orders  []order            `json:"orders"`
}

type quote struct {
	Price    float64 `json:"price"`
	Currency string  `json:"currency"`
	Delivery string  `json:"delivery"`
}

type response struct {
	Quotes  map[string]quote `json:"quotes"`
	Unknown []string         `json:"unknown"`
}

// ---- Levenshtein (fastest-levenshtein semantics: distance over UTF-16 code units) ----

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

// matchProduct returns the catalog name with the smallest distance to the ordered
// name when that distance is at most 2. Ties go to the alphabetically first name.
func matchProduct(product string, names []string) (string, bool) {
	best := -1
	bestName := ""
	for _, name := range names { // names are sorted ascending
		d := levenshtein(product, name)
		if best < 0 || d < best {
			best = d
			bestName = name
		}
	}
	if best < 0 || best > 2 {
		return "", false
	}
	return bestName, true
}

// ---- VAT (libs/Tax) ----

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

// vatRate returns the standard VAT rate, or false for an unknown country.
func vatRate(country string) (float64, bool) {
	r, ok := vatStandard[normCountry(country)]
	return r, ok
}

// reverseCharge is true when a business customer in another EU country pays no VAT.
func reverseCharge(country string, business bool) bool {
	c := normCountry(country)
	return business && c != "SE" && vatEU[c]
}

// ---- Road distance (libs/geo) ----

const earthRadiusKm = 6371.0

func distanceKm(lat1, lon1, lat2, lon2 float64) float64 {
	p1 := lat1 * math.Pi / 180
	p2 := lat2 * math.Pi / 180
	dp := (lat2 - lat1) * math.Pi / 180
	dl := (lon2 - lon1) * math.Pi / 180
	s1 := math.Sin(dp / 2)
	s2 := math.Sin(dl / 2)
	a := s1*s1 + math.Cos(p1)*math.Cos(p2)*(s2*s2)
	return 2.0 * earthRadiusKm * math.Asin(math.Sqrt(a))
}

// roadKm is the great-circle distance times a detour factor of 1.25.
func roadKm(lat1, lon1, lat2, lon2 float64) float64 {
	return distanceKm(lat1, lon1, lat2, lon2) * 1.25
}

// ---- Swedish working days (libs/calendar) ----

var holidays2026 = map[string]bool{
	"2026-01-01": true, "2026-01-06": true, "2026-04-03": true, "2026-04-06": true,
	"2026-05-01": true, "2026-05-14": true, "2026-06-06": true, "2026-06-19": true,
	"2026-12-24": true, "2026-12-25": true, "2026-12-26": true, "2026-12-31": true,
}

func isWorkday(d time.Time) bool {
	wd := d.Weekday()
	if wd == time.Saturday || wd == time.Sunday {
		return false
	}
	return !holidays2026[d.Format("2006-01-02")]
}

// nextWorkday returns the first working day strictly after the given ISO date.
func nextWorkday(iso string) (string, error) {
	d, err := time.Parse("2006-01-02", iso)
	if err != nil {
		return "", err
	}
	d = d.AddDate(0, 0, 1)
	for !isWorkday(d) {
		d = d.AddDate(0, 0, 1)
	}
	return d.Format("2006-01-02"), nil
}

// expressDelivery returns the order date itself when it is a working day, otherwise the next working day after it.
func expressDelivery(iso string) (string, error) {
	d, err := time.Parse("2006-01-02", iso)
	if err != nil {
		return "", err
	}
	if isWorkday(d) {
		return d.Format("2006-01-02"), nil
	}
	return nextWorkday(iso)
}

// ---- Pricing ----

// round2 rounds to 2 decimals the way Python's round(x, 2) does, using the exact binary value.
func round2(x float64) float64 {
	v, err := strconv.ParseFloat(strconv.FormatFloat(x, 'f', 2, 64), 64)
	if err != nil {
		return x
	}
	return v
}

func main() {
	var req request
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		fmt.Fprintln(os.Stderr, "invalid input:", err)
		os.Exit(1)
	}

	names := make([]string, 0, len(req.Catalog))
	for name := range req.Catalog {
		names = append(names, name)
	}
	sort.Strings(names)

	resp := response{Quotes: map[string]quote{}, Unknown: []string{}}

	for _, o := range req.Orders {
		name, ok := matchProduct(o.Product, names)
		if !ok {
			resp.Unknown = append(resp.Unknown, o.ID)
			continue
		}
		zone, err := tariff.Zone(o.Country)
		if err != nil {
			resp.Unknown = append(resp.Unknown, o.ID)
			continue
		}
		var delivery string
		if o.Express {
			delivery, err = expressDelivery(o.Date)
		} else {
			delivery, err = nextWorkday(o.Date)
		}
		if err != nil {
			resp.Unknown = append(resp.Unknown, o.ID)
			continue
		}

		qty := 1.0
		if o.Qty != nil {
			qty = *o.Qty
		}
		weight := qty * req.Catalog[name]
		base := 0.0
		// Business parcels of 50 kg or more ship free: the base price is 0.
		if !(o.Business && weight >= 50) {
			base = tariff.BasePrice(zone, weight)
		}
		if o.Express {
			base *= 1.5
		}
		net := base
		road := roadKm(req.Depot.Lat, req.Depot.Lon, o.Lat, o.Lon)
		if road > 300 {
			// The distance surcharge is capped at 400 SEK per order.
			net += math.Min((road-300)*0.80, 400)
		}

		vat := 0.0
		if !reverseCharge(o.Country, o.Business) {
			r, ok := vatRate(o.Country)
			if !ok {
				resp.Unknown = append(resp.Unknown, o.ID)
				continue
			}
			vat = r
		}

		sek := round2(net * (1 + vat))
		q := quote{Price: sek, Currency: "SEK", Delivery: delivery}
		if normCountry(o.Country) != "SE" {
			rate, ok := req.Rates["EUR"]
			if !ok || rate <= 0 {
				resp.Unknown = append(resp.Unknown, o.ID)
				continue
			}
			q.Price = round2(sek / rate)
			q.Currency = "EUR"
		}
		resp.Quotes[o.ID] = q
	}

	sort.Strings(resp.Unknown)

	out, err := json.Marshal(resp)
	if err != nil {
		fmt.Fprintln(os.Stderr, "encode failed:", err)
		os.Exit(1)
	}
	fmt.Println(string(out))
}
