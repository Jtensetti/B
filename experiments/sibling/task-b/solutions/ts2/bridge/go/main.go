// Bridge: reads a JSON array of H:MM strings on stdin, prints a JSON array of {ok, value}.
package main

import (
	"encoding/json"
	"io"
	"os"

	"example.com/hours"
)

type result struct {
	OK    bool    `json:"ok"`
	Value float64 `json:"value"`
}

func main() {
	in, err := io.ReadAll(os.Stdin)
	if err != nil {
		os.Exit(1)
	}
	var texts []string
	if err := json.Unmarshal(in, &texts); err != nil {
		os.Exit(1)
	}
	out := make([]result, len(texts))
	for i, t := range texts {
		v, err := hours.Parse(t)
		out[i] = result{OK: err == nil, Value: v}
	}
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		os.Exit(1)
	}
}
