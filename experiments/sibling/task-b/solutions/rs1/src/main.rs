use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::io::{self, Read};

// ---- Port of libs/hours (Go): Parse(text) -> hours ----
fn parse_hours(text: &str) -> Option<f64> {
    let parts: Vec<&str> = text.trim().split(':').collect();
    if parts.len() != 2 || parts[1].len() != 2 {
        return None;
    }
    let h: i64 = parts[0].parse().ok()?;
    if h < 0 {
        return None;
    }
    let m: i64 = parts[1].parse().ok()?;
    if !(0..=59).contains(&m) {
        return None;
    }
    Some(h as f64 + m as f64 / 60.0)
}

// ---- Port of libs/Rules (C#): Overtime.Multiplier(weekday) ----
fn multiplier(weekday: &str) -> f64 {
    match weekday {
        "Mon" | "Tue" | "Wed" | "Thu" | "Fri" => 1.0,
        "Sat" => 1.5,
        "Sun" => 2.0,
        _ => panic!("unknown weekday {weekday}"),
    }
}

// Weekday name of a YYYY-MM-DD date (Sakamoto's algorithm).
fn weekday_of(date: &str) -> Option<&'static str> {
    let p: Vec<&str> = date.split('-').collect();
    if p.len() != 3 {
        return None;
    }
    let mut y: i64 = p[0].parse().ok()?;
    let m: i64 = p[1].parse().ok()?;
    let d: i64 = p[2].parse().ok()?;
    if !(1..=12).contains(&m) || !(1..=31).contains(&d) {
        return None;
    }
    const T: [i64; 12] = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4];
    if m < 3 {
        y -= 1;
    }
    let dow = (y + y / 4 - y / 100 + y / 400 + T[(m - 1) as usize] + d).rem_euclid(7);
    Some(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dow as usize])
}

// ---- Port of libs/payroll (Python): withholding(gross, table) ----
fn withholding(gross: f64, table: i64) -> i64 {
    let rate = table as f64 / 100.0;
    let taxable = (gross - 2000.0).max(0.0);
    let low = taxable.min(48000.0) * rate;
    let high = (gross - 50000.0).max(0.0) * (rate + 0.20);
    (low + high).floor() as i64
}

// ---- Port of node_modules/semver: satisfies(version, range) ----
// Supports comparator sets (>=, >, <=, <, =, bare version) joined by spaces,
// alternatives joined by "||". Prerelease versions only satisfy a comparator set
// that names a prerelease on the same major.minor.patch (npm default behaviour).
#[derive(Debug, Clone, PartialEq, Eq)]
struct Version {
    core: (u64, u64, u64),
    pre: Vec<String>,
}

fn parse_version(s: &str) -> Option<Version> {
    let s = s.trim();
    let s = s.strip_prefix('v').or_else(|| s.strip_prefix('=')).unwrap_or(s);
    let s = s.split('+').next()?; // build metadata is ignored
    let (core, pre) = match s.split_once('-') {
        Some((c, p)) => (c, Some(p)),
        None => (s, None),
    };
    let nums: Vec<&str> = core.split('.').collect();
    if nums.len() != 3 {
        return None;
    }
    let mut n = [0u64; 3];
    for (i, part) in nums.iter().enumerate() {
        if part.is_empty() || !part.bytes().all(|b| b.is_ascii_digit()) || (part.len() > 1 && part.starts_with('0')) {
            return None;
        }
        n[i] = part.parse().ok()?;
    }
    let pre = match pre {
        None => Vec::new(),
        Some(p) => {
            let ids: Vec<String> = p.split('.').map(|x| x.to_string()).collect();
            for id in &ids {
                if id.is_empty() || !id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-') {
                    return None;
                }
                if id.bytes().all(|b| b.is_ascii_digit()) && id.len() > 1 && id.starts_with('0') {
                    return None;
                }
            }
            ids
        }
    };
    Some(Version { core: (n[0], n[1], n[2]), pre })
}

fn cmp_pre_id(a: &str, b: &str) -> std::cmp::Ordering {
    use std::cmp::Ordering::*;
    let an = a.bytes().all(|c| c.is_ascii_digit());
    let bn = b.bytes().all(|c| c.is_ascii_digit());
    match (an, bn) {
        (true, true) => a.len().cmp(&b.len()).then_with(|| a.cmp(b)),
        (true, false) => Less,
        (false, true) => Greater,
        (false, false) => a.cmp(b),
    }
}

fn cmp_version(a: &Version, b: &Version) -> std::cmp::Ordering {
    use std::cmp::Ordering::*;
    match a.core.cmp(&b.core) {
        Equal => {}
        o => return o,
    }
    match (a.pre.is_empty(), b.pre.is_empty()) {
        (true, true) => return Equal,
        (true, false) => return Greater,
        (false, true) => return Less,
        _ => {}
    }
    for (x, y) in a.pre.iter().zip(b.pre.iter()) {
        match cmp_pre_id(x, y) {
            Equal => {}
            o => return o,
        }
    }
    a.pre.len().cmp(&b.pre.len())
}

// One comparator: (operator, version).
fn parse_comparator(s: &str) -> Option<(&'static str, Version)> {
    let s = s.trim();
    for op in [">=", "<=", ">", "<", "="] {
        if let Some(rest) = s.strip_prefix(op) {
            let v = parse_version(rest)?;
            let op: &'static str = match op {
                ">=" => ">=",
                "<=" => "<=",
                ">" => ">",
                "<" => "<",
                _ => "=",
            };
            return Some((op, v));
        }
    }
    Some(("=", parse_version(s)?))
}

fn satisfies(version: &str, range: &str) -> bool {
    let Some(v) = parse_version(version) else {
        return false;
    };
    for alt in range.split("||") {
        let mut comparators = Vec::new();
        for tok in alt.split_whitespace() {
            match parse_comparator(tok) {
                Some(c) => comparators.push(c),
                None => {
                    comparators.clear();
                    comparators.push(("<", Version { core: (0, 0, 0), pre: vec!["0".into()] })); // invalid: never matches
                    break;
                }
            }
        }
        if comparators.is_empty() {
            continue;
        }
        // Prerelease versions need a comparator on the same major.minor.patch with a prerelease.
        if !v.pre.is_empty()
            && !comparators
                .iter()
                .any(|(_, c)| !c.pre.is_empty() && c.core == v.core)
        {
            continue;
        }
        let ok = comparators.iter().all(|(op, c)| {
            use std::cmp::Ordering::*;
            let o = cmp_version(&v, c);
            match *op {
                ">=" => o != Less,
                ">" => o == Greater,
                "<=" => o != Greater,
                "<" => o == Less,
                _ => o == Equal,
            }
        });
        if ok {
            return true;
        }
    }
    false
}

// ---- Input / output ----
#[derive(Deserialize)]
struct Input {
    month: String,
    employees: Vec<Employee>,
    shifts: Vec<Shift>,
    #[serde(default)]
    holidays: Vec<String>,
}

// Port of Overtime.Holiday(): multiplier for a public holiday, whatever the weekday.
fn holiday_multiplier() -> f64 {
    2.0
}

#[derive(Deserialize)]
struct Employee {
    id: String,
    hourly: f64,
    table: i64,
    contract: String,
}

#[derive(Deserialize)]
struct Shift {
    id: String,
    employee: String,
    date: String,
    hours: String,
    #[serde(default, rename = "break")]
    brk: Option<String>,
}

#[derive(Serialize)]
struct Payslip {
    hours: f64,
    gross: f64,
    tax: i64,
    net: f64,
    pension: f64,
}

#[derive(Serialize)]
struct Output {
    payslips: BTreeMap<String, Payslip>,
    rejected: Vec<String>,
}

fn round2(x: f64) -> f64 {
    (x * 100.0).round() / 100.0
}

fn main() {
    let mut text = String::new();
    io::stdin().read_to_string(&mut text).expect("read stdin");
    let input: Input = serde_json::from_str(&text).expect("valid input JSON");

    let rates: BTreeMap<&str, &Employee> = input.employees.iter().map(|e| (e.id.as_str(), e)).collect();

    // Per employee: (sum of rounded hours, sum of unrounded pay).
    let mut acc: BTreeMap<&str, (f64, f64)> = input.employees.iter().map(|e| (e.id.as_str(), (0.0, 0.0))).collect();
    let mut rejected: Vec<String> = Vec::new();

    for s in &input.shifts {
        // Shifts outside the payroll month are ignored, not rejected.
        if s.date.get(..7) != Some(input.month.as_str()) {
            continue;
        }
        let Some(emp) = rates.get(s.employee.as_str()) else {
            rejected.push(s.id.clone());
            continue;
        };
        let Some(span) = parse_hours(&s.hours) else {
            rejected.push(s.id.clone());
            continue;
        };
        let brk = match &s.brk {
            None => 0.0,
            Some(b) => match parse_hours(b) {
                Some(b) => b,
                None => {
                    rejected.push(s.id.clone());
                    continue;
                }
            },
        };
        if brk > span {
            rejected.push(s.id.clone());
            continue;
        }
        let Some(wd) = weekday_of(&s.date) else {
            rejected.push(s.id.clone());
            continue;
        };
        let hours = quarter::round_up(span - brk);
        let rate = if satisfies(&emp.contract, ">=3.0.0") { emp.hourly * 1.1 } else { emp.hourly };
        let factor = if input.holidays.iter().any(|h| h == &s.date) {
            holiday_multiplier()
        } else {
            multiplier(wd)
        };
        let pay = hours * rate * factor;
        let entry = acc.get_mut(s.employee.as_str()).expect("employee present");
        entry.0 += hours;
        entry.1 += pay;
    }

    let mut payslips = BTreeMap::new();
    for emp in &input.employees {
        let (hours, pay) = acc[emp.id.as_str()];
        let gross = round2(pay);
        let tax = withholding(gross, emp.table);
        let net = round2(gross - tax as f64);
        // Pension 4.5 % of gross, computed in whole ore (hundredths of a kronor) to avoid
        // float boundary errors; half up. Employer-paid, so it does not affect tax or net.
        let gross_ore = (gross * 100.0).round() as i64;
        let pension_ore = (gross_ore * 45 + 500) / 1000;
        let pension = pension_ore as f64 / 100.0;
        payslips.insert(emp.id.clone(), Payslip { hours, gross, tax, net, pension });
    }

    rejected.sort();
    let out = Output { payslips, rejected };
    println!("{}", serde_json::to_string(&out).expect("serialize"));
}
