// Batch helper: reads a JSON array of H:MM strings on stdin and writes a JSON array
// of hours (or null where hours.Parse fails).
package main

import (
	"encoding/json"
	"io"
	"os"

	"example.com/hours"
)

func main() {
	data, err := io.ReadAll(os.Stdin)
	if err != nil {
		os.Exit(1)
	}
	var texts []string
	if err := json.Unmarshal(data, &texts); err != nil {
		os.Exit(1)
	}
	out := make([]*float64, len(texts))
	for i, t := range texts {
		h, err := hours.Parse(t)
		if err == nil {
			out[i] = &h
		}
	}
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		os.Exit(1)
	}
}
