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
	MaxSek   int64      `json:"max_sek"`
	Legs     []LegInput `json:"legs"`
}

type QuoteResponse struct {
	Legs           int   `json:"legs"`
	ValidLegs      int   `json:"valid_legs"`
	TotalM         int64 `json:"total_m"`
	TotalEurCents  int64 `json:"total_eur_cents"`
	TotalSek       int64 `json:"total_sek"`
	HeavyLegs      int   `json:"heavy_legs"`
	CustomsLegs    int   `json:"customs_legs"`
	LongHaulPairs  int   `json:"long_haul_pairs"`
	VipExempt      int   `json:"vip_exempt"`
	WithinCap      bool  `json:"within_cap"`
	MaxLegEurCents int64 `json:"max_leg_eur_cents"`
}

var depotPattern = regexp.MustCompile(`^[a-z]{3}-[0-9]{2}$`)

func normalizeDepot(route string) string {
	return path.Base(path.Clean(route))
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

func roundToEvenInt(v float64) int64 {
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

func applyZoneAdjustment(legEur float64, zone string) float64 {
	switch zone {
	case "SE":
		return legEur * 0.9
	case "NON-EU":
		return legEur + 15.0
	default:
		return legEur
	}
}

func computeQuote(req QuoteRequest) QuoteResponse {
	validLegs := 0
	heavyLegs := 0
	customsLegs := 0
	longHaulPairs := 0
	vipExempt := 0
	prevLongHaul := false
	totalKm := 0.0
	totalEur := 0.0
	maxLegEurCents := int64(0)

	for _, leg := range req.Legs {
		depot := normalizeDepot(leg.Route)
		zone := normalizeZone(leg.Zone)
		if !depotPattern.MatchString(depot) || !isValidZone(zone) {
			continue
		}

		km := math.Sqrt(leg.DxKm*leg.DxKm + leg.DyKm*leg.DyKm)
		kg := leg.WeightG / 1000.0
		baseEur := 5.0 + 0.5*km + 2.0*kg
		legEur := baseEur * distanceMultiplier(km)
		if kg >= 10.0 {
			heavyLegs++
			if depot == "sto-01" && zone == "SE" {
				vipExempt++
			} else {
				legEur += 12.0
			}
		}
		legEur = applyZoneAdjustment(legEur, zone)
		if zone == "NON-EU" {
			customsLegs++
		}

		isLongHaul := km > 100.0
		if prevLongHaul && isLongHaul {
			longHaulPairs++
		}
		prevLongHaul = isLongHaul

		legEurCents := roundToEvenInt(legEur * 100.0)
		if validLegs == 0 || legEurCents > maxLegEurCents {
			maxLegEurCents = legEurCents
		}

		validLegs++
		totalKm += km
		totalEur += legEur
	}

	totalEur += 25.0 * float64(longHaulPairs)
	totalSek := roundToEvenInt(totalEur * req.EurToSek)

	return QuoteResponse{
		Legs:           len(req.Legs),
		ValidLegs:      validLegs,
		TotalM:         roundToEvenInt(totalKm * 1000.0),
		TotalEurCents:  roundToEvenInt(totalEur * 100.0),
		TotalSek:       totalSek,
		HeavyLegs:      heavyLegs,
		CustomsLegs:    customsLegs,
		LongHaulPairs:  longHaulPairs,
		VipExempt:      vipExempt,
		WithinCap:      totalSek <= req.MaxSek,
		MaxLegEurCents: maxLegEurCents,
	}
}

func main() {
	var req QuoteRequest
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		fmt.Fprintf(os.Stderr, "failed to decode input: %v\n", err)
		os.Exit(1)
	}

	resp := computeQuote(req)
	if err := json.NewEncoder(os.Stdout).Encode(resp); err != nil {
		fmt.Fprintf(os.Stderr, "failed to encode output: %v\n", err)
		os.Exit(1)
	}
}
