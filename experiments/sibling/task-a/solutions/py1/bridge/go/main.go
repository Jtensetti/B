// Bridge to libs/tariff. Reads {"items": [{"country": "SE", "weight": 1.2}, ...]} on stdin and
// writes {"results": [{"served": true, "zone": 1, "base": 57.5}, ...]} on stdout.
package main

import (
	"encoding/json"
	"io"
	"os"

	"example.com/tariff"
)

type item struct {
	Country string  `json:"country"`
	Weight  float64 `json:"weight"`
}

type result struct {
	Served bool    `json:"served"`
	Zone   int     `json:"zone"`
	Base   float64 `json:"base"`
}

func main() {
	raw, err := io.ReadAll(os.Stdin)
	if err != nil {
		panic(err)
	}
	var req struct {
		Items []item `json:"items"`
	}
	if err := json.Unmarshal(raw, &req); err != nil {
		panic(err)
	}
	results := make([]result, 0, len(req.Items))
	for _, it := range req.Items {
		zone, err := tariff.Zone(it.Country)
		if err != nil {
			results = append(results, result{})
			continue
		}
		results = append(results, result{Served: true, Zone: zone, Base: tariff.BasePrice(zone, it.Weight)})
	}
	if err := json.NewEncoder(os.Stdout).Encode(map[string]any{"results": results}); err != nil {
		panic(err)
	}
}
