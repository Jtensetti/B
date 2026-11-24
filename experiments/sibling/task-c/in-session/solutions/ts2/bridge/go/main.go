// Command bridge prints every supplier from Suppliers() with its delivery days, one per line,
// as "name<TAB>days". Days that fail print "ERR" in place of the number.
package main

import (
	"bufio"
	"fmt"
	"os"

	"example.com/leadtime"
)

func main() {
	out := bufio.NewWriter(os.Stdout)
	defer out.Flush()
	for _, name := range leadtime.Suppliers() {
		d, err := leadtime.Days(name)
		if err != nil {
			fmt.Fprintf(out, "%s\tERR\n", name)
		} else {
			fmt.Fprintf(out, "%s\t%d\n", name, d)
		}
	}
}
