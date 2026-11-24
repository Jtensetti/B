// Package tariff holds the carrier's parcel tariff. Maintained by the logistics team.
package tariff

import (
	"errors"
	"math"
	"strings"
)

var zones = map[string]int{
	"SE": 1, "NO": 2, "DK": 2, "FI": 2, "DE": 3, "NL": 3, "PL": 3, "FR": 4, "ES": 4, "IT": 4,
}

// start and perKg are in SEK, excluding VAT.
var start = map[int]float64{1: 49, 2: 79, 3: 99, 4: 129}
var perKg = map[int]float64{1: 6.5, 2: 9.0, 3: 11.0, 4: 14.5}

// Zone returns the tariff zone (1-4) for an ISO country code, or an error if the carrier does not serve it.
func Zone(country string) (int, error) {
	z, ok := zones[strings.ToUpper(strings.TrimSpace(country))]
	if !ok {
		return 0, errors.New("country not served: " + country)
	}
	return z, nil
}

// BasePrice is the carrier price in SEK excluding VAT for a parcel of the given weight in kilograms.
// Weight is rounded up to the next half kilogram.
func BasePrice(zone int, weightKg float64) float64 {
	billed := math.Ceil(weightKg*2) / 2
	return start[zone] + perKg[zone]*billed
}
