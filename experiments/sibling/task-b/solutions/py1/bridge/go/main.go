// Bridge: reads a JSON array of H:MM strings on stdin, writes a JSON array of
// {"value": hours} or {"error": message} using libs/hours.Parse.
package main

import (
	"encoding/json"
	"io"
	"os"

	"example.com/hours"
)

type result struct {
	Value *float64 `json:"value,omitempty"`
	Error *string  `json:"error,omitempty"`
}

func main() {
	data, err := io.ReadAll(os.Stdin)
	if err != nil {
		os.Exit(1)
	}
	var texts []string
	if err := json.Unmarshal(data, &texts); err != nil {
		os.Exit(1)
	}
	out := make([]result, 0, len(texts))
	for _, t := range texts {
		v, err := hours.Parse(t)
		if err != nil {
			msg := err.Error()
			out = append(out, result{Error: &msg})
			continue
		}
		out = append(out, result{Value: &v})
	}
	enc, err := json.Marshal(out)
	if err != nil {
		os.Exit(1)
	}
	os.Stdout.Write(enc)
}
