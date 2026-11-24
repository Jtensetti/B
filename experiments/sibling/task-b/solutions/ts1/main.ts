// Monthly payslips. Reads one JSON line on stdin, writes one JSON line on stdout.
// The libraries in libs/ are in other languages, so each is called once per run through a
// small driver in drivers/ that takes and returns JSON.
import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import { createRequire } from "node:module";
import * as path from "node:path";

const ROOT: string = import.meta.dirname;

// npm semver, from node_modules. It ships without type declarations, so it is loaded with require.
const semver = createRequire(import.meta.url)("semver") as {
  satisfies(version: string, range: string): boolean;
};

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
  break?: string;
}

interface Input {
  month: string;
  employees: Employee[];
  shifts: Shift[];
  holidays?: string[];
}

interface Result<T> {
  ok: boolean;
  value: T;
  error: string | null;
}

interface Payslip {
  hours: number;
  gross: number;
  tax: number;
  net: number;
  pension: number;
}

// Runs a driver with the given items as a JSON array and returns one result per item.
// An empty batch is not sent at all.
function callDriver<T>(dir: string, cmd: string, args: string[], items: unknown[]): Result<T>[] {
  if (items.length === 0) {
    return [];
  }
  const stdout = execFileSync(cmd, args, {
    cwd: path.join(ROOT, "drivers", dir),
    input: JSON.stringify(items),
    encoding: "utf8",
    stdio: ["pipe", "pipe", "inherit"],
  });
  // Build tools may print progress lines before the result; the result is the last line.
  const lines = stdout.trim().split("\n");
  const parsed: unknown = JSON.parse(lines[lines.length - 1]);
  if (!Array.isArray(parsed) || parsed.length !== items.length) {
    throw new Error(`driver ${dir} returned a bad batch`);
  }
  return parsed as Result<T>[];
}

// Round to 2 decimals, removing binary floating-point noise first.
function round2(x: number): number {
  return Math.round((x + Number.EPSILON) * 100) / 100;
}

// Weekday name ("Mon".."Sun") of a YYYY-MM-DD date, computed in UTC so the time zone does not matter.
function weekdayOf(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  const names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  return names[new Date(Date.UTC(y, m - 1, d)).getUTCDay()];
}

// Hourly rate for an employee. Contract version >=3.0.0 gets 10 % more.
// Prerelease versions such as 3.1.0-rc.1 do not satisfy the range (npm semver rules).
function hourlyRate(e: Employee): number {
  return semver.satisfies(e.contract, ">=3.0.0") ? e.hourly * 1.1 : e.hourly;
}

function run(input: Input): { payslips: Record<string, Payslip>; rejected: string[] } {
  // Only shifts dated in the month count. Others are ignored, not rejected.
  const shifts = input.shifts.filter((s) => s.date.startsWith(input.month + "-"));

  const employees = new Map<string, Employee>();
  for (const e of input.employees) {
    employees.set(e.id, e);
  }

  // 1. Parse every shift's hours, and its break where it has one, with the time-reporting library.
  const texts = [
    ...shifts.map((s) => s.hours),
    ...shifts.filter((s) => s.break !== undefined).map((s) => s.break as string),
  ];
  const parsed = callDriver<number>("hours", "go", ["run", "."], texts);
  let nextBreak = shifts.length;

  const rejected: string[] = [];
  const parsedShifts: { shift: Shift; employee: Employee | undefined; raw: number | null }[] = [];

  shifts.forEach((shift, i) => {
    const h = parsed[i];
    let raw: number | null = h.ok ? h.value : null;
    if (shift.break !== undefined) {
      // Worked time is hours minus break. A break that cannot be parsed, or longer than the hours, rejects the shift.
      const b = parsed[nextBreak++];
      raw = h.ok && b.ok && b.value <= h.value ? h.value - b.value : null;
    }
    parsedShifts.push({ shift, employee: employees.get(shift.employee), raw });
  });

  // 2. Round the good hours up to the quarter hour.
  const good = parsedShifts.filter((p) => p.employee !== undefined && p.raw !== null);
  const rounded = callDriver<number>("quarter", "cargo", ["run", "-q"], good.map((p) => p.raw));

  // 3. Overtime multiplier per shift: the holiday multiplier on a public holiday, otherwise from the weekday of its date.
  const holidays = new Set(input.holidays ?? []);
  const multipliers = callDriver<number>(
    "rules",
    "dotnet",
    ["run", "-v", "q", "--project", "."],
    good.map((p) => (holidays.has(p.shift.date) ? "holiday" : weekdayOf(p.shift.date))),
  );

  good.forEach((p, i) => {
    if (!multipliers[i].ok) {
      throw new Error(`shift ${p.shift.id}: ${multipliers[i].error}`);
    }
  });

  for (const p of parsedShifts) {
    if (p.employee === undefined || p.raw === null) {
      rejected.push(p.shift.id);
    }
  }
  rejected.sort();

  // Totals per employee: hours and gross pay (shift pay is hours x hourly x multiplier).
  const totals = new Map<string, { hours: number; pay: number }>();
  for (const e of input.employees) {
    totals.set(e.id, { hours: 0, pay: 0 });
  }
  good.forEach((p, i) => {
    if (!p.employee) {
      return;
    }
    const t = totals.get(p.employee.id);
    if (!t) {
      return;
    }
    t.hours += rounded[i].value;
    t.pay += rounded[i].value * hourlyRate(p.employee) * multipliers[i].value;
  });

  // 4. Withholding tax per employee, from the library in libs/payroll.
  const grosses = input.employees.map((e) => round2(totals.get(e.id)?.pay ?? 0));
  const taxes = callDriver<number>(
    "payroll",
    "python3",
    ["-B", "driver.py"],
    input.employees.map((e, i) => [grosses[i], e.table]),
  );

  const payslips: Record<string, Payslip> = {};
  input.employees.forEach((e, i) => {
    const t = totals.get(e.id) ?? { hours: 0, pay: 0 };
    const tax = taxes[i];
    if (!tax.ok) {
      throw new Error(`employee ${e.id}: ${tax.error}`);
    }
    const gross = grosses[i];
    payslips[e.id] = {
      hours: t.hours,
      gross,
      tax: tax.value,
      net: round2(gross - tax.value),
      // Employer-paid pension: 4.5 % of gross. It does not change tax or net.
      pension: round2(gross * 0.045),
    };
  });

  return { payslips, rejected };
}

const input: Input = JSON.parse(fs.readFileSync(0, "utf8"));
const result = run(input);
process.stdout.write(JSON.stringify(result) + "\n");
