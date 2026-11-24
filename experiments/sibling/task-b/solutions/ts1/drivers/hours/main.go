// Driver: reads a JSON array of strings on stdin and prints, for each, the result of hours.Parse.
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
	Error string  `json:"error"`
}

func main() {
	data, err := io.ReadAll(os.Stdin)
	if err != nil {
		os.Exit(2)
	}
	var texts []string
	if err := json.Unmarshal(data, &texts); err != nil {
		os.Stderr.WriteString(err.Error())
		os.Exit(2)
	}
	out := make([]result, len(texts))
	for i, t := range texts {
		v, err := hours.Parse(t)
		if err != nil {
			out[i] = result{Error: err.Error()}
		} else {
			out[i] = result{OK: true, Value: v}
		}
	}
	json.NewEncoder(os.Stdout).Encode(out)
}
