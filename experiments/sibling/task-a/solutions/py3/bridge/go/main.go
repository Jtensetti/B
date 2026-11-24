// Command tariffq reads a JSON array of {"country","weight"} from stdin and
// prints a JSON array of {"ok","base"} using the tariff library.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"example.com/tariff"
)

type req struct {
	Country string  `json:"country"`
	Weight  float64 `json:"weight"`
}

type resp struct {
	OK   bool    `json:"ok"`
	Base float64 `json:"base"`
}

func main() {
	var reqs []req
	if err := json.NewDecoder(os.Stdin).Decode(&reqs); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	out := make([]resp, len(reqs))
	for i, r := range reqs {
		zone, err := tariff.Zone(r.Country)
		if err != nil {
			out[i] = resp{OK: false}
			continue
		}
		out[i] = resp{OK: true, Base: tariff.BasePrice(zone, r.Weight)}
	}
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
