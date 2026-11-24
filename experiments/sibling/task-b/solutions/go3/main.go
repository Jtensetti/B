// Command payslips reads a payroll month as JSON on stdin and writes payslips as JSON on stdout.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"os/exec"
	"sort"
	"strings"
	"time"

	"example.com/hours"
)

type employee struct {
	ID     string  `json:"id"`
	Hourly float64 `json:"hourly"`
	Table  int     `json:"table"`
	// Contract is part of the input format but no rule uses it.
	Contract string `json:"contract"`
}

type shift struct {
	ID       string  `json:"id"`
	Employee string  `json:"employee"`
	Date     string  `json:"date"`
	Hours    string  `json:"hours"`
	Break    *string `json:"break"`
}

type input struct {
	Month     string     `json:"month"`
	Employees []employee `json:"employees"`
	Shifts    []shift    `json:"shifts"`
	Holidays  []string   `json:"holidays"`
}

type payslip struct {
	Hours   float64 `json:"hours"`
	Gross   float64 `json:"gross"`
	Tax     int     `json:"tax"`
	Net     float64 `json:"net"`
	Pension float64 `json:"pension"`
}

type output struct {
	Payslips map[string]payslip `json:"payslips"`
	Rejected []string           `json:"rejected"`
}

// seniorRange is the contract range that earns a 10 % higher hourly rate.
const seniorRange = ">=3.0.0"

// semverScript evaluates node_modules/semver (npm) for each contract on stdin (a JSON array of
// strings) and writes a JSON object mapping contract to whether it satisfies seniorRange.
const semverScript = `
const path = require("path");
const semver = require(path.resolve("node_modules/semver"));
const range = process.argv[1];
let data = "";
process.stdin.on("data", (c) => (data += c));
process.stdin.on("end", () => {
  const out = {};
  for (const v of JSON.parse(data)) out[v] = semver.satisfies(v, range);
  process.stdout.write(JSON.stringify(out));
});
`

// seniorContracts returns, for each contract string, whether it satisfies seniorRange.
func seniorContracts(contracts []string) (map[string]bool, error) {
	result := make(map[string]bool, len(contracts))
	if len(contracts) == 0 {
		return result, nil
	}
	in, err := json.Marshal(contracts)
	if err != nil {
		return nil, err
	}
	cmd := exec.Command("node", "-e", semverScript, seniorRange)
	cmd.Stdin = bytes.NewReader(in)
	cmd.Stderr = os.Stderr
	out, err := cmd.Output()
	if err != nil {
		return nil, fmt.Errorf("semver check via node: %w", err)
	}
	if err := json.Unmarshal(out, &result); err != nil {
		return nil, fmt.Errorf("semver check output: %w", err)
	}
	return result, nil
}

// roundUp is a port of libs/quarter (Rust): rounds hours up to the next quarter hour.
func roundUp(h float64) float64 {
	quarters := h * 4.0
	tolerance := 4.0 / 3600.0
	return math.Max(math.Ceil(quarters-tolerance), 0) / 4.0
}

// multiplier is a port of libs/Rules (C#) Overtime.Multiplier.
func multiplier(weekday string) float64 {
	switch weekday {
	case "Mon", "Tue", "Wed", "Thu", "Fri":
		return 1.0
	case "Sat":
		return 1.5
	case "Sun":
		return 2.0
	}
	panic("unknown weekday " + weekday)
}

// holidayMultiplier is a port of libs/Rules (C#) Overtime.Holiday.
func holidayMultiplier() float64 {
	return 2.0
}

// withholding is a port of libs/payroll (Python) withholding.withholding.
func withholding(gross float64, table int) int {
	rate := float64(table) / 100
	taxable := math.Max(0, gross-2000)
	low := math.Min(taxable, 48000) * rate
	high := math.Max(0, gross-50000) * (rate + 0.20)
	return int(math.Floor(low + high))
}

func round2(x float64) float64 {
	return math.Round(x*100) / 100
}

func run(r io.Reader, w io.Writer) error {
	var in input
	if err := json.NewDecoder(r).Decode(&in); err != nil {
		return fmt.Errorf("read input: %w", err)
	}

	rates := make(map[string]employee, len(in.Employees))
	hoursBy := make(map[string]float64)
	grossBy := make(map[string]float64)
	contracts := make([]string, 0, len(in.Employees))
	for _, e := range in.Employees {
		rates[e.ID] = e
		hoursBy[e.ID] = 0
		grossBy[e.ID] = 0
		contracts = append(contracts, e.Contract)
	}
	senior, err := seniorContracts(contracts)
	if err != nil {
		return err
	}
	holiday := make(map[string]bool, len(in.Holidays))
	for _, d := range in.Holidays {
		holiday[d] = true
	}
	hourlyBy := make(map[string]float64, len(in.Employees))
	for _, e := range in.Employees {
		hourlyBy[e.ID] = e.Hourly
		if senior[e.Contract] {
			hourlyBy[e.ID] = e.Hourly * 1.10
		}
	}

	rejected := []string{}
	for _, s := range in.Shifts {
		if !strings.HasPrefix(s.Date, in.Month+"-") {
			continue
		}
		emp, ok := rates[s.Employee]
		if !ok {
			rejected = append(rejected, s.ID)
			continue
		}
		parsed, err := hours.Parse(s.Hours)
		if err != nil {
			rejected = append(rejected, s.ID)
			continue
		}
		if s.Break != nil {
			brk, err := hours.Parse(*s.Break)
			if err != nil || brk > parsed {
				rejected = append(rejected, s.ID)
				continue
			}
			parsed -= brk
		}
		date, err := time.Parse("2006-01-02", s.Date)
		if err != nil {
			return fmt.Errorf("shift %s: bad date %q: %w", s.ID, s.Date, err)
		}
		h := roundUp(parsed)
		mult := holidayMultiplier()
		if !holiday[s.Date] {
			mult = multiplier(date.Weekday().String()[:3])
		}
		pay := h * hourlyBy[emp.ID] * mult
		hoursBy[emp.ID] += h
		grossBy[emp.ID] += pay
	}
	sort.Strings(rejected)

	payslips := make(map[string]payslip, len(in.Employees))
	for _, e := range in.Employees {
		gross := round2(grossBy[e.ID])
		tax := withholding(gross, e.Table)
		payslips[e.ID] = payslip{
			Hours:   hoursBy[e.ID],
			Gross:   gross,
			Tax:     tax,
			Net:     gross - float64(tax),
			Pension: round2(gross * 0.045),
		}
	}

	enc := json.NewEncoder(w)
	return enc.Encode(output{Payslips: payslips, Rejected: rejected})
}

func main() {
	if err := run(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
