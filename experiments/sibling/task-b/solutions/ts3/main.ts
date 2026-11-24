import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

// ---- npm semver (node_modules/semver, no bundled types) -----------------

const nodeRequire = createRequire(process.argv[1]!);
const semver = nodeRequire("semver") as {
  satisfies(version: string, range: string): boolean;
};

// ---- Types for the input line -------------------------------------------

interface Employee {
  id: string;
  hourly: number;
  table: number;
  contract: string;
}

interface Shift {
  id: string;
  employee: string;
  date: string;
  hours: string;
  break?: string | null;
}

interface Input {
  month: string;
  employees: Employee[];
  shifts: Shift[];
  holidays?: string[] | null;
}

interface Payslip {
  hours: number;
  gross: number;
  pension: number;
  tax: number;
  net: number;
}

interface Output {
  payslips: Record<string, Payslip>;
  rejected: string[];
}

// ---- Port of libs/hours (Go): Parse(text) (float64, error) ---------------
// Returns null where the Go version returns an error.

const GO_INT = /^[+-]?[0-9]+$/;
const INT64_MAX = 9223372036854775807n;

function goAtoi(s: string): number | null {
  if (!GO_INT.test(s)) return null;
  const big = BigInt(s);
  if (big > INT64_MAX || big < -INT64_MAX - 1n) return null;
  return Number(big);
}

function parseHours(text: string): number | null {
  // Go strings.TrimSpace, then strings.Split(text, ":")
  const parts = text.trim().split(":");
  if (parts.length !== 2 || parts[1].length !== 2) return null;
  const h = goAtoi(parts[0]);
  if (h === null || h < 0) return null;
  const m = goAtoi(parts[1]);
  if (m === null || m < 0 || m > 59) return null;
  return h + m / 60.0;
}

// ---- Port of libs/quarter (Rust): round_up(hours) -> f64 ---------------

function roundUp(hours: number): number {
  const quarters = hours * 4.0;
  const tolerance = 4.0 / 3600.0;
  return Math.max(Math.ceil(quarters - tolerance), 0) / 4.0;
}

// ---- Port of libs/Rules (C#): Overtime.Multiplier(weekday) -------------

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function multiplier(weekday: string): number {
  switch (weekday) {
    case "Mon":
    case "Tue":
    case "Wed":
    case "Thu":
    case "Fri":
      return 1.0;
    case "Sat":
      return 1.5;
    case "Sun":
      return 2.0;
    default:
      throw new Error("unknown weekday " + weekday);
  }
}

// Port of Overtime.Holiday(): multiplier for a public holiday.
function holidayMultiplier(): number {
  return 2.0;
}

// Weekday of a YYYY-MM-DD date, computed in UTC so the local zone cannot shift it.
function weekdayOf(date: string): string {
  const [y, m, d] = date.split("-").map((p) => Number(p));
  const day = new Date(Date.UTC(y, m - 1, d)).getUTCDay();
  return WEEKDAYS[day];
}

// ---- Port of libs/payroll (Python): withholding(gross, table) -> int ----

function withholding(gross: number, table: number): number {
  const rate = table / 100;
  const taxable = Math.max(0.0, gross - 2000);
  const low = Math.min(taxable, 48000) * rate;
  const high = Math.max(0.0, gross - 50000) * (rate + 0.2);
  return Math.floor(low + high);
}

// ---- Sorting helper: code point order, as Python's sorted() does --------

function compareCodePoints(a: string, b: string): number {
  const x = Array.from(a);
  const y = Array.from(b);
  const n = Math.min(x.length, y.length);
  for (let i = 0; i < n; i++) {
    const d = x[i].codePointAt(0)! - y[i].codePointAt(0)!;
    if (d !== 0) return d;
  }
  return x.length - y.length;
}

// ---- Payroll run --------------------------------------------------------

function run(input: Input): Output {
  const holidays = new Set<string>(input.holidays ?? []);
  const employees = new Map<string, Employee>();
  for (const e of input.employees) employees.set(e.id, e);

  // Contract version >= 3.0.0 gets a 10 % higher hourly rate.
  // Prereleases do not satisfy the range (npm semver default).
  const rates = new Map<string, number>();
  for (const e of input.employees) {
    const bonus = semver.satisfies(e.contract, ">=3.0.0") ? 1.1 : 1.0;
    rates.set(e.id, e.hourly * bonus);
  }

  const totals = new Map<string, { hours: number; gross: number }>();
  for (const e of input.employees) totals.set(e.id, { hours: 0, gross: 0 });

  const rejected: string[] = [];

  for (const s of input.shifts) {
    // Only shifts dated in the payroll month count. Others are ignored, not rejected.
    if (s.date.slice(0, 7) !== input.month) continue;
    const emp = employees.get(s.employee);
    const parsed = parseHours(s.hours);
    // Worked time is the shift minus an optional break. A break that cannot
    // be parsed, or that is longer than the shift, rejects the shift.
    let worked = parsed;
    if (s.break !== undefined && s.break !== null) {
      const brk = parseHours(s.break);
      if (parsed === null || brk === null || brk > parsed) {
        worked = null;
      } else {
        worked = parsed - brk;
      }
    }
    if (emp === undefined || worked === null) {
      rejected.push(s.id);
      continue;
    }
    const hours = roundUp(worked);
    // A public holiday pays the holiday multiplier, whatever the weekday.
    const mult = holidays.has(s.date) ? holidayMultiplier() : multiplier(weekdayOf(s.date));
    const pay = hours * rates.get(emp.id)! * mult;
    const t = totals.get(emp.id)!;
    t.hours += hours;
    t.gross += pay;
  }

  const payslips: Record<string, Payslip> = {};
  for (const e of input.employees) {
    const t = totals.get(e.id)!;
    const gross = Math.round(t.gross * 100) / 100;
    // Employer-paid pension: does not change tax or net.
    const pension = Math.round(gross * 0.045 * 100) / 100;
    const tax = withholding(gross, e.table);
    payslips[e.id] = {
      hours: t.hours,
      gross,
      pension,
      tax,
      net: gross - tax,
    };
  }

  rejected.sort(compareCodePoints);
  return { payslips, rejected };
}

// ---- Entry point --------------------------------------------------------

const raw = readFileSync(0, "utf8");
const input = JSON.parse(raw) as Input;
process.stdout.write(JSON.stringify(run(input)) + "\n");
