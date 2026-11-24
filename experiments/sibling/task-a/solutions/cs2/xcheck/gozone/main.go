package main

import (
	"bufio"
	"fmt"
	"os"

	"example.com/tariff"
)

func main() {
	sc := bufio.NewScanner(os.Stdin)
	for sc.Scan() {
		z, err := tariff.Zone(sc.Text())
		if err != nil {
			fmt.Println("ERR")
		} else {
			fmt.Println(z)
		}
	}
}
