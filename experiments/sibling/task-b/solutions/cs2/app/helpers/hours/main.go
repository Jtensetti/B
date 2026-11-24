// Command hourshelper reads one JSON string per line from stdin, runs hours.Parse on it
// and writes the hours per line, or "ERR" when Parse fails.
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"strconv"

	"example.com/hours"
)

func main() {
	in := bufio.NewScanner(os.Stdin)
	in.Buffer(make([]byte, 1<<20), 1<<28)
	out := bufio.NewWriter(os.Stdout)
	defer out.Flush()
	for in.Scan() {
		var text string
		if err := json.Unmarshal(in.Bytes(), &text); err != nil {
			fmt.Fprintln(out, "ERR")
			continue
		}
		h, err := hours.Parse(text)
		if err != nil {
			fmt.Fprintln(out, "ERR")
			continue
		}
		fmt.Fprintln(out, strconv.FormatFloat(h, 'f', -1, 64))
	}
}
