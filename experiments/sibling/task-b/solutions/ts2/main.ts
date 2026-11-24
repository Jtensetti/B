import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import * as path from 'node:path';
import { createRequire } from 'node:module';

// Monthly payslip run. Each library is called through a small bridge in its own language,
// batched so that every bridge runs at most once per invocation.

const ROOT = path.dirname(path.resolve(process.argv[1]));
const LIBS = path.join(ROOT, 'libs');
const BRIDGE = path.join(ROOT, 'bridge');

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
  holidays?: string[];
}

interface Payslip {
  hours: number;
  gross: number;
  tax: number;
  net: number;
  pension: number;
}

interface ParseResult {
  ok: boolean;
  value: number;
}

// npm semver (node_modules/semver), CommonJS.
const semver: { satisfies(version: string, range: string): boolean } =
  createRequire(path.join(ROOT, 'main.ts'))('semver');

const RAISE_RANGE = '>=3.0.0';

const HOLIDAY = 'Holiday';
const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function run(cmd: string, args: string[], cwd: string, input: string): string {
  return execFileSync(cmd, args, {
    cwd,
    input,
    encoding: 'utf8',
    stdio: ['pipe', 'pipe', 'inherit'],
  });
}

// hours library (Go): H:MM -> hours, with ok flag.
function parseHours(texts: string[]): ParseResult[] {
  if (texts.length === 0) return [];
  const out = run('go', ['run', '.'], path.join(BRIDGE, 'go'), JSON.stringify(texts));
  return JSON.parse(out) as ParseResult[];
}

// quarter library (Rust): round hours up to the next quarter hour.
function roundUp(values: number[]): number[] {
  if (values.length === 0) return [];
  const out = run(
    'cargo',
    ['run', '-q'],
    path.join(BRIDGE, 'rust'),
    values.map((v) => String(v)).join('\n') + '\n',
  );
  return out
    .split('\n')
    .filter((line) => line.trim() !== '')
    .map((line) => Number(line));
}

// Rules library (C#): overtime multiplier per weekday name, or Holiday for public holidays.
function multipliers(days: string[]): number[] {
  if (days.length === 0) return [];
  const out = run(
    'dotnet',
    ['run', '-v', 'q', '--project', path.join(BRIDGE, 'cs', 'Bridge.csproj')],
    ROOT,
    JSON.stringify(days),
  );
  return JSON.parse(out) as number[];
}

// payroll library (Python): tax to withhold, whole kronor.
function withholdings(items: { gross: number; table: number }[]): number[] {
  if (items.length === 0) return [];
  const script = [
    'import sys, json',
    'sys.path.insert(0, sys.argv[1])',
    'from withholding import withholding',
    'items = json.load(sys.stdin)',
    'print(json.dumps([withholding(g, t) for g, t in items]))',
  ].join('\n');
  const out = run(
    'python3',
    ['-B', '-c', script, path.join(LIBS, 'payroll')],
    ROOT,
    JSON.stringify(items.map((i) => [i.gross, i.table])),
  );
  return JSON.parse(out) as number[];
}

function validDate(date: string): boolean {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!m) return false;
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return d.getUTCFullYear() === Number(m[1]) &&
    d.getUTCMonth() === Number(m[2]) - 1 &&
    d.getUTCDate() === Number(m[3]);
}

// Multiplier key for a shift: public holidays use the Holiday rule, otherwise the weekday.
function multKey(date: string, holidays: Set<string>): string {
  return holidays.has(date) ? HOLIDAY : weekday(date);
}

function weekday(date: string): string {
  const [y, mo, d] = date.split('-').map(Number);
  return WEEKDAYS[new Date(Date.UTC(y, mo - 1, d)).getUTCDay()];
}

// Round half up to 2 decimals, first removing binary floating-point noise.
function round2(x: number): number {
  return Math.round(Number((x * 100).toPrecision(12))) / 100;
}

function main(): void {
  const input = JSON.parse(readFileSync(0, 'utf8')) as Input;
  const employees = new Map<string, Employee>();
  for (const e of input.employees) employees.set(e.id, e);

  const rejected: string[] = [];

  // Shifts with an unknown employee or an invalid date are rejected up front.
  const candidates: Shift[] = [];
  for (const s of input.shifts) {
    // Shifts outside the payslip month are ignored: neither paid nor rejected.
    if (typeof s.date !== 'string' || s.date.slice(0, 7) !== input.month) continue;
    if (!employees.has(s.employee) || !validDate(s.date)) {
      rejected.push(s.id);
    } else {
      candidates.push(s);
    }
  }

  // One Go call for all hours and breaks: the hours come first, then the breaks that are present.
  const n = candidates.length;
  const breakIdx: number[] = [];
  candidates.forEach((s, i) => {
    if (s.break != null) breakIdx.push(i);
  });
  const parsed = parseHours([
    ...candidates.map((s) => s.hours),
    ...breakIdx.map((i) => candidates[i].break as string),
  ]);
  const breakParsed: (ParseResult | undefined)[] = candidates.map(() => undefined);
  breakIdx.forEach((ci, k) => {
    breakParsed[ci] = parsed[n + k];
  });

  // Worked time is the shift length minus the break. A bad break, or a break longer than the shift, rejects it.
  const valid: { shift: Shift; hours: number }[] = [];
  candidates.forEach((shift, i) => {
    const h = parsed[i];
    const b = breakParsed[i];
    if (!h.ok) {
      rejected.push(shift.id);
    } else if (b === undefined) {
      valid.push({ shift, hours: h.value });
    } else if (!b.ok || b.value > h.value) {
      rejected.push(shift.id);
    } else {
      valid.push({ shift, hours: h.value - b.value });
    }
  });

  const rounded = roundUp(valid.map((v) => v.hours));
  const holidays = new Set(input.holidays ?? []);
  const days = [...new Set(valid.map((v) => multKey(v.shift.date, holidays)))];
  const mults = new Map<string, number>();
  const multValues = multipliers(days);
  days.forEach((d, i) => mults.set(d, multValues[i]));

  const totals = new Map<string, { hours: number; gross: number }>();
  for (const id of employees.keys()) totals.set(id, { hours: 0, gross: 0 });

  valid.forEach((v, i) => {
    const emp = employees.get(v.shift.employee)!;
    const h = rounded[i];
    const rate = semver.satisfies(emp.contract, RAISE_RANGE) ? emp.hourly * 1.1 : emp.hourly;
    const pay = h * rate * mults.get(multKey(v.shift.date, holidays))!;
    const t = totals.get(emp.id)!;
    t.hours += h;
    t.gross += pay;
  });

  const ids = input.employees.map((e) => e.id);
  const taxes = withholdings(
    ids.map((id) => ({ gross: round2(totals.get(id)!.gross), table: employees.get(id)!.table })),
  );

  const payslips: Record<string, Payslip> = {};
  ids.forEach((id, i) => {
    const t = totals.get(id)!;
    const gross = round2(t.gross);
    const tax = taxes[i];
    // Employer-paid pension: 4.5 % of gross. Does not affect tax or net.
    const pension = round2(gross * 0.045);
    payslips[id] = { hours: t.hours, gross, tax, net: round2(gross - tax), pension };
  });

  rejected.sort();
  process.stdout.write(JSON.stringify({ payslips, rejected }) + '\n');
}

main();
