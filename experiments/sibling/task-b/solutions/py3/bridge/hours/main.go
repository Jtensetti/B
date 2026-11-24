// Driver: reads a JSON array of strings on stdin, writes a JSON array with the
// parsed hours, or null where hours.Parse returns an error.
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
			v := h
			out[i] = &v
		}
	}
	enc, err := json.Marshal(out)
	if err != nil {
		os.Exit(1)
	}
	os.Stdout.Write(enc)
	os.Stdout.Write([]byte("\n"))
}
