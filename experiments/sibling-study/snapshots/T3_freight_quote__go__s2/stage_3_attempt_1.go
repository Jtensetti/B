package main

import (
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path"
	"regexp"
	"strings"
)

type Leg struct {
	Route   string  `json:"route"`
	DxKm    float64 `json:"dx_km"`
	DyKm    float64 `json:"dy_km"`
	WeightG float64 `json:"weight_g"`
	Zone    string  `json:"zone"`
}

type QuoteRequest struct {
	EurToSek float64 `json:"eur_to_sek"`
	Legs     []Leg   `json:"legs"`
}

type QuoteResponse struct {
	Legs          int   `json:"legs"`
	ValidLegs     int   `json:"valid_legs"`
	TotalM        int64 `json:"total_m"`
	TotalEurCents int64 `json:"total_eur_cents"`
	TotalSek      int64 `json:"total_sek"`
	HeavyLegs     int   `json:"heavy_legs"`
	CustomsLegs   int   `json:"customs_legs"`
	LongHaulPairs int   `json:"long_haul_pairs"`
}

var depotRegex = regexp.MustCompile(`^[a-z]{3}-[0-9]{2}$`)

func normalizeDepot(route string) string {
	norm := path.Clean(route)
	return path.Base(norm)
}

func normalizeZone(zone string) string {
	return strings.ToUpper(strings.TrimSpace(zone))
}

func isValidZone(zone string) bool {
	switch zone {
	case "SE", "EU", "NON-EU":
		return true
	default:
		return false
	}
}

func roundHalfToEven(v float64) int64 {
	return int64(math.RoundToEven(v))
}

func distanceMultiplier(km float64) float64 {
	if km <= 50.0 {
		return 1.0
	}
	if km <= 200.0 {
		return 1.15
	}
	return 1.35
}

func computeQuote(req QuoteRequest) QuoteResponse {
	validLegs := 0
	heavyLegs := 0
	customsLegs := 0
	longHaulPairs := 0
	prevLongHaul := false
	totalKm := 0.0
	totalEur := 0.0

	for _, leg := range req.Legs {
		depot := normalizeDepot(leg.Route)
		zone := normalizeZone(leg.Zone)
		if !depotRegex.MatchString(depot) || !isValidZone(zone) {
			continue
		}

		validLegs++
		km := math.Sqrt(leg.DxKm*leg.DxKm + leg.DyKm*leg.DyKm)
		kg := leg.WeightG / 1000.0
		baseEur := 5.0 + 0.5*km + 2.0*kg
		legEur := baseEur * distanceMultiplier(km)
		if kg >= 10.0 {
			heavyLegs++
			legEur += 12.0
		}

		switch zone {
		case "SE":
			legEur *= 0.9
		case "NON-EU":
			customsLegs++
			legEur += 15.0
		}

		isLongHaul := km > 100.0
		if prevLongHaul && isLongHaul {
			longHaulPairs++
		}
		prevLongHaul = isLongHaul

		totalKm += km
		totalEur += legEur
	}

	totalEur += 25.0 * float64(longHaulPairs)

	return QuoteResponse{
		Legs:          len(req.Legs),
		ValidLegs:     validLegs,
		TotalM:        roundHalfToEven(totalKm * 1000.0),
		TotalEurCents: roundHalfToEven(totalEur * 100.0),
		TotalSek:      roundHalfToEven(totalEur * req.EurToSek),
		HeavyLegs:     heavyLegs,
		CustomsLegs:   customsLegs,
		LongHaulPairs: longHaulPairs,
	}
}

func main() {
	var req QuoteRequest
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		fmt.Fprintf(os.Stderr, "failed to decode input: %v\n", err)
		os.Exit(1)
	}

	resp := computeQuote(req)
	enc := json.NewEncoder(os.Stdout)
	if err := enc.Encode(resp); err != nil {
		fmt.Fprintf(os.Stderr, "failed to encode output: %v\n", err)
		os.Exit(1)
	}
}
