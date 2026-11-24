// Command payslip reads one line of JSON describing a month of shifts from
// standard input and writes one line of JSON with the payslips and the
// rejected shift ids.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"sort"
	"time"

	"example.com/hours"
)

type Employee struct {
	ID       string  `json:"id"`
	Hourly   float64 `json:"hourly"`
	Table    int     `json:"table"`
	Contract string  `json:"contract"`
}

type Shift struct {
	ID       string  `json:"id"`
	Employee string  `json:"employee"`
	Date     string  `json:"date"`
	Hours    string  `json:"hours"`
	Break    *string `json:"break"`
}

type Input struct {
	Month     string     `json:"month"`
	Employees []Employee `json:"employees"`
	Shifts    []Shift    `json:"shifts"`
	Holidays  []string   `json:"holidays"`
}

type Payslip struct {
	Hours float64 `json:"hours"`
	Gross float64 `json:"gross"`
	Tax   int64   `json:"tax"`
	Net   float64 `json:"net"`
	// Pension is paid by the employer; it does not change tax or net.
	Pension float64 `json:"pension"`
}

type Output struct {
	Payslips map[string]Payslip `json:"payslips"`
	Rejected []string           `json:"rejected"`
}

// roundUp is a port of libs/quarter (Rust round_up): rounds hours up to the
// next quarter hour, with a one-second tolerance.
func roundUp(h float64) float64 {
	quarters := float64(h * 4.0)
	tolerance := 4.0 / 3600.0
	return math.Max(math.Ceil(float64(quarters-tolerance)), 0) / 4.0
}

// multiplier is a port of libs/Rules (C# Overtime.Multiplier) for a weekday.
func multiplier(wd time.Weekday) float64 {
	switch wd {
	case time.Saturday:
		return 1.5
	case time.Sunday:
		return 2.0
	default:
		return 1.0
	}
}

// overtimeHoliday is a port of libs/Rules (C# Overtime.Holiday).
func overtimeHoliday() float64 {
	return 2.0
}

// withholding is a port of libs/payroll/withholding.py.
func withholding(gross float64, table int) int64 {
	rate := float64(table) / 100
	taxable := math.Max(0, gross-2000)
	low := float64(math.Min(taxable, 48000) * rate)
	high := float64(math.Max(0, gross-50000) * (rate + 0.20))
	return int64(math.Floor(float64(low + high)))
}

// pension is 4.5 % of gross, rounded to two decimals (half up), computed in
// whole öre so that no binary floating-point noise can move a tie.
func pension(gross float64) float64 {
	cents := int64(math.Round(gross * 100))
	return float64((cents*45+500)/1000) / 100
}

// round2 rounds to two decimals, halves away from zero.
func round2(x float64) float64 {
	return math.Round(x*100) / 100
}

func run(in Input) Output {
	type acc struct {
		hours float64
		gross float64
	}
	byEmp := make(map[string]*acc, len(in.Employees))
	rates := make(map[string]Employee, len(in.Employees))
	holiday := make(map[string]bool, len(in.Holidays))
	for _, d := range in.Holidays {
		holiday[d] = true
	}
	for _, e := range in.Employees {
		byEmp[e.ID] = &acc{}
		// Contract versions in the >=3.0.0 range earn a 10 % higher hourly rate.
		if satisfies(e.Contract, ">=3.0.0") {
			e.Hourly = e.Hourly * 1.1
		}
		rates[e.ID] = e
	}

	rejected := []string{}
	for _, s := range in.Shifts {
		// Only shifts dated in the payslip month count; others are ignored, not rejected.
		if len(s.Date) < 7 || s.Date[:7] != in.Month {
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
		// Worked time is the shift minus its unpaid break, if it has one.
		if s.Break != nil {
			brk, err := hours.Parse(*s.Break)
			if err != nil || brk > parsed {
				rejected = append(rejected, s.ID)
				continue
			}
			parsed -= brk
		}
		day, err := time.Parse("2006-01-02", s.Date)
		if err != nil {
			rejected = append(rejected, s.ID)
			continue
		}
		h := roundUp(parsed)
		a := byEmp[s.Employee]
		a.hours += h
		mult := multiplier(day.Weekday())
		if holiday[s.Date] {
			mult = overtimeHoliday()
		}
		a.gross += h * emp.Hourly * mult
	}
	sort.Strings(rejected)

	payslips := make(map[string]Payslip, len(in.Employees))
	for _, e := range in.Employees {
		a := byEmp[e.ID]
		gross := round2(a.gross)
		tax := withholding(gross, e.Table)
		payslips[e.ID] = Payslip{
			Hours:   a.hours,
			Gross:   gross,
			Tax:     tax,
			Net:     round2(gross - float64(tax)),
			Pension: pension(gross),
		}
	}
	return Output{Payslips: payslips, Rejected: rejected}
}

func main() {
	data, err := io.ReadAll(os.Stdin)
	if err != nil {
		fmt.Fprintln(os.Stderr, "read stdin:", err)
		os.Exit(1)
	}
	var in Input
	if err := json.Unmarshal(data, &in); err != nil {
		fmt.Fprintln(os.Stderr, "parse input:", err)
		os.Exit(1)
	}
	out, err := json.Marshal(run(in))
	if err != nil {
		fmt.Fprintln(os.Stderr, "encode output:", err)
		os.Exit(1)
	}
	fmt.Println(string(out))
}
