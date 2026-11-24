// Command payslips computes monthly payslips from one line of JSON on stdin.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"os/exec"
	"sort"
	"strconv"
	"strings"
	"time"

	"example.com/hours"
)

type employee struct {
	ID       string  `json:"id"`
	Hourly   float64 `json:"hourly"`
	Table    int     `json:"table"`
	Contract string  `json:"contract"`
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

// accepted is a shift whose employee is known and whose hours parsed.
type accepted struct {
	shift   shift
	raw     float64
	weekday string
	hours   float64 // rounded up to the quarter hour
	pay     float64
}

func main() {
	if err := run(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "payslips:", err)
		os.Exit(1)
	}
}

func run(stdin *os.File, stdout *os.File) error {
	var in input
	if err := json.NewDecoder(stdin).Decode(&in); err != nil {
		return fmt.Errorf("bad input: %w", err)
	}
	known := make(map[string]employee, len(in.Employees))
	slips := make(map[string]payslip, len(in.Employees))
	for _, e := range in.Employees {
		known[e.ID] = e
		slips[e.ID] = payslip{}
	}

	// Effective hourly rate: contracts in the bonus range get 10 % more.
	emps := make([]employee, len(in.Employees))
	copy(emps, in.Employees)
	sort.Slice(emps, func(i, j int) bool { return emps[i].ID < emps[j].ID })
	contracts := make([]string, len(emps))
	for i, e := range emps {
		contracts[i] = e.Contract
	}
	bonus, err := helper(contracts, "node", "-e", semverScript)
	if err != nil {
		return err
	}
	rate := make(map[string]float64, len(emps))
	for i, e := range emps {
		rate[e.ID] = e.Hourly
		if bonus[i] == "true" {
			rate[e.ID] = e.Hourly * 110 / 100
		}
	}

	rejected := []string{}
	var acc []accepted
	for _, s := range in.Shifts {
		d, err := time.Parse("2006-01-02", s.Date)
		if err != nil {
			return fmt.Errorf("shift %s: bad date: %w", s.ID, err)
		}
		if d.Format("2006-01") != in.Month {
			continue // other months are ignored, not rejected
		}
		if _, ok := known[s.Employee]; !ok {
			rejected = append(rejected, s.ID)
			continue
		}
		raw, err := hours.Parse(s.Hours)
		if err != nil {
			rejected = append(rejected, s.ID)
			continue
		}
		if s.Break != nil {
			brk, err := hours.Parse(*s.Break)
			if err != nil || brk > raw {
				rejected = append(rejected, s.ID)
				continue
			}
			raw -= brk
		}
		acc = append(acc, accepted{shift: s, raw: raw, weekday: d.Weekday().String()[:3]})
	}

	// Round hours up to the quarter hour via libs/quarter (Rust).
	lines := make([]string, len(acc))
	for i, a := range acc {
		lines[i] = strconv.FormatFloat(a.raw, 'g', -1, 64)
	}
	rounded, err := helper(lines, "cargo", "run", "--quiet", "--manifest-path", "bridge/quarter/Cargo.toml")
	if err != nil {
		return err
	}
	for i := range acc {
		if acc[i].hours, err = strconv.ParseFloat(rounded[i], 64); err != nil {
			return fmt.Errorf("quarter: %w", err)
		}
	}

	// Overtime multiplier per weekday, or the holiday multiplier, via libs/Rules (C#).
	holiday := make(map[string]bool, len(in.Holidays))
	for _, h := range in.Holidays {
		holiday[h] = true
	}
	days := make([]string, len(acc))
	for i, a := range acc {
		days[i] = a.weekday
		if holiday[a.shift.Date] {
			days[i] = "holiday"
		}
	}
	mults, err := helper(days, "dotnet", "run", "--project", "bridge/rules", "--verbosity", "quiet")
	if err != nil {
		return err
	}
	for i := range acc {
		m, err := strconv.ParseFloat(mults[i], 64)
		if err != nil {
			return fmt.Errorf("rules: %s: %w", mults[i], err)
		}
		a := &acc[i]
		a.pay = a.hours * rate[a.shift.Employee] * m
	}

	// Sum per employee.
	for _, a := range acc {
		p := slips[a.shift.Employee]
		p.Hours += a.hours
		p.Gross += a.pay
		slips[a.shift.Employee] = p
	}

	// Withholding per employee via libs/payroll (Python).
	ids := make([]string, 0, len(slips))
	for id := range slips {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	wl := make([]string, len(ids))
	for i, id := range ids {
		p := slips[id]
		p.Gross = round2(p.Gross)
		slips[id] = p
		wl[i] = strconv.FormatFloat(p.Gross, 'f', 2, 64) + " " + strconv.Itoa(known[id].Table)
	}
	taxes, err := helper(wl, "python3", "-B", "-c",
		"import sys; sys.path.insert(0, 'libs/payroll'); from withholding import withholding\n"+
			"for line in sys.stdin:\n    g, t = line.split()\n    print(withholding(float(g), int(t)))")
	if err != nil {
		return err
	}
	for i, id := range ids {
		p := slips[id]
		tax, err := strconv.Atoi(strings.TrimSpace(taxes[i]))
		if err != nil {
			return fmt.Errorf("payroll: %w", err)
		}
		p.Tax = tax
		p.Net = round2(p.Gross - float64(tax))
		p.Pension = pension(p.Gross)
		p.Hours = round2(p.Hours)
		slips[id] = p
	}

	sort.Strings(rejected)
	enc := json.NewEncoder(stdout)
	return enc.Encode(output{Payslips: slips, Rejected: rejected})
}

// bonusRange is the contract range that earns the 10 % rate bonus.
const bonusRange = ">=3.0.0"

// semverScript reads one contract version per stdin line and prints "true" or "false"
// for whether it satisfies bonusRange, using libs node_modules/semver (npm semantics).
var semverScript = "const semver = require(require('path').resolve('node_modules/semver'));" +
	"const rl = require('readline').createInterface({ input: process.stdin });" +
	"rl.on('line', l => console.log(String(semver.satisfies(l.trim(), '" + bonusRange + "'))));"

// pension is 4.5 % of gross, rounded half up to 2 decimals, computed in whole cents.
func pension(gross float64) float64 {
	cents := int64(math.Round(gross * 100))
	return float64((cents*45+500)/1000) / 100
}

func round2(x float64) float64 {
	return math.Round(x*100) / 100
}

// helper runs a line-oriented program: one input line in, one output line out.
func helper(lines []string, name string, args ...string) ([]string, error) {
	if len(lines) == 0 {
		return nil, nil
	}
	cmd := exec.Command(name, args...)
	cmd.Stdin = strings.NewReader(strings.Join(lines, "\n") + "\n")
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("%s: %w: %s", name, err, strings.TrimSpace(stderr.String()))
	}
	out := strings.Split(strings.TrimSpace(stdout.String()), "\n")
	if len(out) != len(lines) {
		return nil, fmt.Errorf("%s: got %d lines, want %d", name, len(out), len(lines))
	}
	for i := range out {
		out[i] = strings.TrimSpace(out[i])
		if strings.HasPrefix(out[i], "ERR") {
			return nil, fmt.Errorf("%s: %s", name, out[i])
		}
	}
	return out, nil
}
