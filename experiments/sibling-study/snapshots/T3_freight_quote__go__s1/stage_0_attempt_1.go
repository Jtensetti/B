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

type LegInput struct {
	Route   string  `json:"route"`
	DxKm    float64 `json:"dx_km"`
	DyKm    float64 `json:"dy_km"`
	WeightG float64 `json:"weight_g"`
	Zone    string  `json:"zone"`
}

type QuoteRequest struct {
	EurToSek float64    `json:"eur_to_sek"`
	Legs     []LegInput `json:"legs"`
}

type QuoteResponse struct {
	Legs          int   `json:"legs"`
	ValidLegs     int   `json:"valid_legs"`
	TotalM        int64 `json:"total_m"`
	TotalEurCents int64 `json:"total_eur_cents"`
	TotalSek      int64 `json:"total_sek"`
}

var depotPattern = regexp.MustCompile(`^[a-z]{3}-[0-9]{2}$`)

func isValidZone(zone string) bool {
	switch zone {
	case "SE", "EU", "NON-EU":
		return true
	default:
		return false
	}
}

func roundToEvenInt(v float64) int64 {
	return int64(math.RoundToEven(v))
}

func computeQuote(req QuoteRequest) QuoteResponse {
	validLegs := 0
	totalKm := 0.0
	totalEur := 0.0

	for _, leg := range req.Legs {
		norm := path.Clean(leg.Route)
		depot := path.Base(norm)
		zone := strings.ToUpper(strings.TrimSpace(leg.Zone))

		if !depotPattern.MatchString(depot) || !isValidZone(zone) {
			continue
		}

		validLegs++
		km := math.Sqrt(leg.DxKm*leg.DxKm + leg.DyKm*leg.DyKm)
		kg := leg.WeightG / 1000.0
		legEur := 5.0 + 0.5*km + 2.0*kg

		totalKm += km
		totalEur += legEur
	}

	return QuoteResponse{
		Legs:          len(req.Legs),
		ValidLegs:     validLegs,
		TotalM:        roundToEvenInt(totalKm * 1000.0),
		TotalEurCents: roundToEvenInt(totalEur * 100.0),
		TotalSek:      roundToEvenInt(totalEur * req.EurToSek),
	}
}

func main() {
	var req QuoteRequest
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		fmt.Fprintf(os.Stderr, "failed to decode input JSON: %v\n", err)
		os.Exit(1)
	}

	resp := computeQuote(req)
	if err := json.NewEncoder(os.Stdout).Encode(resp); err != nil {
		fmt.Fprintf(os.Stderr, "failed to encode output JSON: %v\n", err)
		os.Exit(1)
	}
}
