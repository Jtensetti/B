// Command delivery reads one JSON request on stdin and writes one JSON response
// with delivery quotes for furniture orders. See BRIEF.md.
//
// The libraries in libs/ are used as follows:
//   - tariff (Go): imported directly.
//   - geo (Rust), Tax (C#), calendar (Python), fastest-levenshtein (npm): run
//     through small driver programs in bridge/, each called once per run with
//     all of its inputs batched.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"os/exec"
	"sort"
	"strconv"
	"strings"

	"example.com/tariff"
)

const (
	maxNameDistance = 2
	freeRoadKm      = 300.0
	extraKmSEK      = 0.80
	expressFactor   = 1.5
	maxSurchargeSEK = 400.0
	freeFreightKg   = 50.0
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
	Qty      *float64 `json:"qty"` // optional, defaults to 1
	Express  bool     `json:"express"`
}

type request struct {
	Depot   point              `json:"depot"`
	Catalog map[string]float64 `json:"catalog"`
	Orders  []order            `json:"orders"`
	Rates   map[string]float64 `json:"rates"` // SEK per unit of each currency
}

type quote struct {
	Price    float64 `json:"price"`
	Delivery string  `json:"delivery"`
	Currency string  `json:"currency"`
}

type response struct {
	Quotes  map[string]quote `json:"quotes"`
	Unknown []string         `json:"unknown"`
}

// candidate is an order that has a matched product and a served country.
type candidate struct {
	order
	weight float64
	zone   int
}

func main() {
	var req request
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		fail(fmt.Errorf("read request: %w", err))
	}

	resp := response{Quotes: map[string]quote{}, Unknown: []string{}}
	unknown := map[string]bool{}
	markUnknown := func(id string) { unknown[id] = true }

	names := make([]string, 0, len(req.Catalog))
	for name := range req.Catalog {
		names = append(names, name)
	}
	sort.Strings(names)

	// Product matching: Levenshtein distance to every catalog name.
	matched := matchProducts(req.Orders, names)

	var cands []candidate
	for i, o := range req.Orders {
		name := matched[i]
		if name == "" {
			markUnknown(o.ID)
			continue
		}
		zone, err := tariff.Zone(o.Country)
		if err != nil {
			markUnknown(o.ID)
			continue
		}
		qty := 1.0
		if o.Qty != nil {
			qty = *o.Qty
		}
		cands = append(cands, candidate{order: o, weight: req.Catalog[name] * qty, zone: zone})
	}

	if len(cands) > 0 {
		road := roadDistances(req.Depot, cands)
		rates := vatRates(cands)
		days := nextWorkdays(cands)

		for i, c := range cands {
			if rates[i].err != "" {
				markUnknown(c.ID)
				continue
			}
			extra := math.Max(0, road[i]-freeRoadKm)
			base := tariff.BasePrice(c.zone, c.weight)
			if c.Business && c.weight >= freeFreightKg {
				base = 0
			}
			if c.Express {
				base *= expressFactor
			}
			surcharge := math.Min(extraKmSEK*extra, maxSurchargeSEK)
			net := base + surcharge
			vat := rates[i].rate
			if rates[i].reverse {
				vat = 0
			}
			price := math.Round(net*(1+vat)*100) / 100
			q := quote{Price: price, Delivery: days[i], Currency: "SEK"}
			if !isSweden(c.Country) {
				eur := req.Rates["EUR"]
				if eur <= 0 {
					fail(fmt.Errorf("missing or non-positive EUR rate in rates"))
				}
				q.Price = math.Round(price/eur*100) / 100
				q.Currency = "EUR"
			}
			resp.Quotes[c.ID] = q
		}
	}

	for id := range unknown {
		resp.Unknown = append(resp.Unknown, id)
	}
	sort.Strings(resp.Unknown)

	out, err := json.Marshal(resp)
	if err != nil {
		fail(err)
	}
	os.Stdout.Write(append(out, '\n'))
}

// matchProducts returns, for each order, the catalog name with the smallest
// Levenshtein distance to the ordered name if that distance is at most
// maxNameDistance, ties going to the alphabetically first name. Otherwise "".
func matchProducts(orders []order, names []string) []string {
	result := make([]string, len(orders))
	if len(names) == 0 || len(orders) == 0 {
		return result
	}

	pairs := make([][2]string, 0, len(orders)*len(names))
	for _, o := range orders {
		for _, n := range names {
			pairs = append(pairs, [2]string{o.Product, n})
		}
	}
	var dists []int
	if err := runJSON(pairs, &dists, "node", "bridge/lev/lev.js"); err != nil {
		fail(fmt.Errorf("levenshtein: %w", err))
	}

	for i := range orders {
		best, bestD := "", -1
		for j, n := range names {
			d := dists[i*len(names)+j]
			// names is sorted, so a strictly smaller distance keeps the
			// alphabetically first name on ties.
			if bestD < 0 || d < bestD {
				best, bestD = n, d
			}
		}
		if bestD >= 0 && bestD <= maxNameDistance {
			result[i] = best
		}
	}
	return result
}

// roadDistances returns the road distance in km from the depot to each candidate.
func roadDistances(depot point, cands []candidate) []float64 {
	var b strings.Builder
	for _, c := range cands {
		fmt.Fprintf(&b, "%s %s %s %s\n",
			ff(depot.Lat), ff(depot.Lon), ff(c.Lat), ff(c.Lon))
	}
	out, err := run(b.String(), "cargo", "run", "--quiet", "--manifest-path", "bridge/geo/Cargo.toml")
	if err != nil {
		fail(fmt.Errorf("geo: %w", err))
	}
	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	if len(lines) != len(cands) {
		fail(fmt.Errorf("geo: got %d results for %d requests", len(lines), len(cands)))
	}
	dists := make([]float64, len(lines))
	for i, l := range lines {
		v, err := strconv.ParseFloat(strings.TrimSpace(l), 64)
		if err != nil {
			fail(fmt.Errorf("geo: parse %q: %w", l, err))
		}
		dists[i] = v
	}
	return dists
}

type vatResult struct {
	Rate    float64 `json:"Rate"`
	Reverse bool    `json:"Reverse"`
	Error   string  `json:"Error"`
}

type vatRate struct {
	rate    float64
	reverse bool
	err     string
}

// vatRates returns the VAT rate and reverse-charge flag for each candidate.
func vatRates(cands []candidate) []vatRate {
	type query struct {
		Country  string `json:"Country"`
		Business bool   `json:"Business"`
	}
	queries := make([]query, len(cands))
	for i, c := range cands {
		queries[i] = query{Country: c.Country, Business: c.Business}
	}
	var results []vatResult
	if err := runJSON(queries, &results, "dotnet", "run", "--project", "bridge/vat", "--no-launch-profile", "-v", "q"); err != nil {
		fail(fmt.Errorf("vat: %w", err))
	}
	if len(results) != len(cands) {
		fail(fmt.Errorf("vat: got %d results for %d requests", len(results), len(cands)))
	}
	out := make([]vatRate, len(results))
	for i, r := range results {
		out[i] = vatRate{rate: r.Rate, reverse: r.Reverse, err: r.Error}
	}
	return out
}

// nextWorkdays returns the first Swedish working day after each candidate's order date.
func nextWorkdays(cands []candidate) []string {
	type dayQuery struct {
		Date    string `json:"date"`
		Express bool   `json:"express"`
	}
	queries := make([]dayQuery, len(cands))
	for i, c := range cands {
		queries[i] = dayQuery{Date: c.Date, Express: c.Express}
	}
	var days []string
	if err := runJSON(queries, &days, "python3", "-I", "bridge/cal/cal.py"); err != nil {
		fail(fmt.Errorf("calendar: %w", err))
	}
	if len(days) != len(cands) {
		fail(fmt.Errorf("calendar: got %d results for %d requests", len(days), len(cands)))
	}
	return days
}

// runJSON sends input as JSON on the child's stdin and decodes its JSON stdout into output.
func runJSON(input any, output any, name string, args ...string) error {
	payload, err := json.Marshal(input)
	if err != nil {
		return err
	}
	out, err := run(string(payload), name, args...)
	if err != nil {
		return err
	}
	return json.Unmarshal(out, output)
}

// run executes a command with stdin as input and returns its stdout.
func run(stdin string, name string, args ...string) ([]byte, error) {
	cmd := exec.Command(name, args...)
	cmd.Stdin = strings.NewReader(stdin)
	cmd.Stderr = os.Stderr
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return nil, err
	}
	return out.Bytes(), nil
}

func isSweden(country string) bool {
	return strings.ToUpper(strings.TrimSpace(country)) == "SE"
}

func ff(x float64) string {
	return strconv.FormatFloat(x, 'f', -1, 64)
}

func fail(err error) {
	fmt.Fprintln(os.Stderr, "error:", err)
	os.Exit(1)
}
