// Bridge to libs/leadtime. Reads {"suppliers":[...]} on stdin and writes
// {"results":[{"ok":bool,"days":int}, ...]} on stdout, one entry per supplier.
// With {"list":true} it writes {"suppliers":[...]} instead.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"example.com/leadtime"
)

type request struct {
	List      bool     `json:"list"`
	Suppliers []string `json:"suppliers"`
}

type result struct {
	OK   bool `json:"ok"`
	Days int  `json:"days"`
}

func main() {
	var req request
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if req.List {
		if err := json.NewEncoder(os.Stdout).Encode(map[string]any{"suppliers": leadtime.Suppliers()}); err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		return
	}
	results := make([]result, 0, len(req.Suppliers))
	for _, s := range req.Suppliers {
		d, err := leadtime.Days(s)
		if err != nil {
			results = append(results, result{OK: false})
			continue
		}
		results = append(results, result{OK: true, Days: d})
	}
	if err := json.NewEncoder(os.Stdout).Encode(map[string]any{"results": results}); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
