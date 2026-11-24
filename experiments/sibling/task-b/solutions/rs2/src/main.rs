//! Monthly payslips. Reads one JSON line on stdin, writes one JSON line on stdout.
//!
//! Ports of the team libraries in libs/ (their behaviour is defined by their code):
//! - hours::parse        (libs/hours/hours.go)
//! - quarter::round_up   (libs/quarter/src/lib.rs)
//! - Overtime::Multiplier / Holiday (libs/Rules/Overtime.cs)
//! - withholding         (libs/payroll/withholding.py)
//! - semver::satisfies   (node_modules/semver, node-semver 7.x range rules, no includePrerelease)

use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::io::{self, Read};

/// Contract versions at or above this get a 10 % higher hourly rate.
const RAISE_RANGE: &str = ">=3.0.0";

/// Employer pension contribution as a share of gross.
const PENSION_RATE: f64 = 0.045;

// ---------------------------------------------------------------- hours

/// Parses "H:MM" into hours. Mirrors hours.go: minutes must be 00-59, hours >= 0.
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

// ---------------------------------------------------------------- quarter

/// Rounds hours up to the next quarter hour, with a one-second tolerance (quarter/src/lib.rs).
fn round_up(hours: f64) -> f64 {
    let quarters = hours * 4.0;
    let tolerance = 4.0 / 3600.0;
    (quarters - tolerance).ceil().max(0.0) / 4.0
}

// ---------------------------------------------------------------- Rules

/// Overtime multiplier for a weekday "Mon".."Sun" (Overtime.cs). None for anything else.
fn multiplier(weekday: &str) -> Option<f64> {
    match weekday {
        "Mon" | "Tue" | "Wed" | "Thu" | "Fri" => Some(1.0),
        "Sat" => Some(1.5),
        "Sun" => Some(2.0),
        _ => None,
    }
}

/// Days since 1970-01-01 for a proleptic Gregorian date.
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let mp = if m > 2 { m - 3 } else { m + 9 };
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

/// Weekday name ("Mon".."Sun") of a "YYYY-MM-DD" date, or None if malformed.
fn weekday_of(date: &str) -> Option<&'static str> {
    let parts: Vec<&str> = date.split('-').collect();
    if parts.len() != 3 || parts[0].len() != 4 || parts[1].len() != 2 || parts[2].len() != 2 {
        return None;
    }
    let y: i64 = parts[0].parse().ok()?;
    let m: i64 = parts[1].parse().ok()?;
    let d: i64 = parts[2].parse().ok()?;
    if !(1..=12).contains(&m) || !(1..=31).contains(&d) {
        return None;
    }
    let days = days_from_civil(y, m, d);
    // 1970-01-01 was a Thursday; index 0 = Sunday.
    let names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    Some(names[(days + 4).rem_euclid(7) as usize])
}

// ---------------------------------------------------------------- payroll

/// Multiplier for a public holiday, whatever the weekday (Overtime.cs Holiday).
fn holiday() -> f64 {
    2.0
}

/// Preliminary withholding in whole kronor (withholding.py).
fn withholding(gross: f64, table: i64) -> i64 {
    let rate = table as f64 / 100.0;
    let taxable = (gross - 2000.0).max(0.0);
    let low = taxable.min(48000.0) * rate;
    let high = (gross - 50000.0).max(0.0) * (rate + 0.20);
    (low + high).floor() as i64
}

// ---------------------------------------------------------------- semver

mod semver {
    use std::cmp::Ordering;

    #[derive(Clone, Debug)]
    pub struct Ver {
        pub major: u64,
        pub minor: u64,
        pub patch: u64,
        pub pre: Vec<String>,
    }

    #[derive(Clone, Copy, Debug)]
    pub enum Op {
        Lt,
        Le,
        Gt,
        Ge,
        Eq,
    }

    #[derive(Clone, Debug)]
    pub enum Cmp {
        Any,
        Never,
        Bound(Op, Ver),
    }

    /// Partial version from a range: each component is None for x/X/*.
    struct Part {
        m: [Option<u64>; 3],
        pre: Vec<String>,
    }

    fn is_num(s: &str) -> bool {
        !s.is_empty() && s.bytes().all(|b| b.is_ascii_digit())
    }

    fn strict_num(s: &str) -> Option<u64> {
        if !is_num(s) || (s.len() > 1 && s.starts_with('0')) {
            return None;
        }
        s.parse().ok()
    }

    fn valid_ids(pre: &str) -> Option<Vec<String>> {
        let mut ids = Vec::new();
        for id in pre.split('.') {
            if id.is_empty() || !id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-') {
                return None;
            }
            if is_num(id) && id.len() > 1 && id.starts_with('0') {
                return None;
            }
            ids.push(id.to_string());
        }
        Some(ids)
    }

    /// Strict semver version: v?MAJOR.MINOR.PATCH(-pre)?(+build)?
    pub fn parse_version(s: &str) -> Option<Ver> {
        let s = s.trim();
        let s = s.strip_prefix('v').unwrap_or(s);
        let (rest, build) = match s.split_once('+') {
            Some((a, b)) => (a, Some(b)),
            None => (s, None),
        };
        if let Some(b) = build {
            if b.is_empty()
                || b.split('.').any(|id| id.is_empty() || !id.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-'))
            {
                return None;
            }
        }
        let (core, pre) = match rest.split_once('-') {
            Some((a, b)) => (a, Some(b)),
            None => (rest, None),
        };
        let parts: Vec<&str> = core.split('.').collect();
        if parts.len() != 3 {
            return None;
        }
        let pre = match pre {
            Some(p) => valid_ids(p)?,
            None => Vec::new(),
        };
        Some(Ver {
            major: strict_num(parts[0])?,
            minor: strict_num(parts[1])?,
            patch: strict_num(parts[2])?,
            pre,
        })
    }

    fn parse_part(s: &str) -> Option<Part> {
        let (core, pre) = match s.split_once('-') {
            Some((a, b)) => (a, Some(b)),
            None => (s, None),
        };
        let pieces: Vec<&str> = core.split('.').collect();
        if pieces.len() > 3 {
            return None;
        }
        let mut m = [None; 3];
        for (i, p) in pieces.iter().enumerate() {
            if matches!(*p, "x" | "X" | "*") {
                continue;
            }
            m[i] = Some(strict_num(p)?);
        }
        // Mirrors node-semver invalidXRangeOrder: an x may not be followed by a number.
        if (m[0].is_none() && m[1].is_some()) || (m[1].is_none() && m[2].is_some()) {
            return None;
        }
        let pre = match pre {
            Some(p) => valid_ids(p)?,
            None => Vec::new(),
        };
        Some(Part { m, pre })
    }

    fn bound(op: Op, major: u64, minor: u64, patch: u64, pre: &[&str]) -> Cmp {
        Cmp::Bound(
            op,
            Ver {
                major,
                minor,
                patch,
                pre: pre.iter().map(|s| s.to_string()).collect(),
            },
        )
    }

    /// Lowest prerelease of the given version, the "-0" bound node-semver uses for upper limits.
    fn lt_zero(major: u64, minor: u64, patch: u64) -> Cmp {
        bound(Op::Lt, major, minor, patch, &["0"])
    }

    fn tilde(p: &Part) -> Vec<Cmp> {
        let [Some(mj), mn, pt] = p.m else { return vec![Cmp::Any] };
        match (mn, pt) {
            (None, _) => vec![bound(Op::Ge, mj, 0, 0, &[]), lt_zero(mj + 1, 0, 0)],
            (Some(mi), None) => vec![bound(Op::Ge, mj, mi, 0, &[]), lt_zero(mj, mi + 1, 0)],
            (Some(mi), Some(pa)) => {
                let pre: Vec<&str> = p.pre.iter().map(|s| s.as_str()).collect();
                vec![bound(Op::Ge, mj, mi, pa, &pre), lt_zero(mj, mi + 1, 0)]
            }
        }
    }

    fn caret(p: &Part) -> Vec<Cmp> {
        let [Some(mj), mn, pt] = p.m else { return vec![Cmp::Any] };
        let pre: Vec<&str> = p.pre.iter().map(|s| s.as_str()).collect();
        let Some(mi) = mn else {
            return vec![bound(Op::Ge, mj, 0, 0, &[]), lt_zero(mj + 1, 0, 0)];
        };
        let Some(pa) = pt else {
            return if mj == 0 {
                vec![bound(Op::Ge, 0, mi, 0, &[]), lt_zero(0, mi + 1, 0)]
            } else {
                vec![bound(Op::Ge, mj, mi, 0, &[]), lt_zero(mj + 1, 0, 0)]
            };
        };
        if mj == 0 {
            if mi == 0 {
                vec![bound(Op::Ge, 0, 0, pa, &pre), lt_zero(0, 0, pa + 1)]
            } else {
                vec![bound(Op::Ge, 0, mi, pa, &pre), lt_zero(0, mi + 1, 0)]
            }
        } else {
            vec![bound(Op::Ge, mj, mi, pa, &pre), lt_zero(mj + 1, 0, 0)]
        }
    }

    /// Plain comparators (=, <, <=, >, >=, or none) including x-range expansion.
    fn xrange(op: &str, p: &Part) -> Vec<Cmp> {
        let [Some(mj), mn, pt] = p.m else {
            return vec![if op == "<" || op == ">" { Cmp::Never } else { Cmp::Any }];
        };
        let xm = mn.is_none();
        let xp = xm || pt.is_none();
        let mi = mn.unwrap_or(0);
        let pa = pt.unwrap_or(0);
        let op = if (op.is_empty() || op == "=") && xp { "" } else { op };
        if xp && matches!(op, ">" | ">=" | "<" | "<=") {
            return vec![match op {
                ">" if xm => bound(Op::Ge, mj + 1, 0, 0, &[]),
                ">" => bound(Op::Ge, mj, mi + 1, 0, &[]),
                ">=" => bound(Op::Ge, mj, mi, 0, &[]),
                "<=" if xm => lt_zero(mj + 1, 0, 0),
                "<=" => lt_zero(mj, mi + 1, 0),
                _ => lt_zero(mj, mi, 0),
            }];
        }
        if op.is_empty() && xp {
            return if xm {
                vec![bound(Op::Ge, mj, 0, 0, &[]), lt_zero(mj + 1, 0, 0)]
            } else {
                vec![bound(Op::Ge, mj, mi, 0, &[]), lt_zero(mj, mi + 1, 0)]
            };
        }
        let pre: Vec<&str> = p.pre.iter().map(|s| s.as_str()).collect();
        let o = match op {
            "<" => Op::Lt,
            "<=" => Op::Le,
            ">" => Op::Gt,
            ">=" => Op::Ge,
            _ => Op::Eq,
        };
        vec![bound(o, mj, mi, pa, &pre)]
    }

    /// One comparator token such as ">=3.0.0", "~1.2", "^0.1.2", "1.x" or "*".
    fn comparator(token: &str) -> Option<Vec<Cmp>> {
        const OPS: [&str; 8] = ["<=", ">=", "~>", "<", ">", "=", "~", "^"];
        let (op, rest) = OPS
            .iter()
            .find(|o| token.starts_with(**o))
            .map(|o| (*o, &token[o.len()..]))
            .unwrap_or(("", token));
        let rest = rest.strip_prefix('v').unwrap_or(rest);
        let rest = rest.split('+').next().unwrap_or("");
        if rest.is_empty() {
            return if op.is_empty() { Some(vec![Cmp::Any]) } else { None };
        }
        let p = parse_part(rest)?;
        Some(match op {
            "~" | "~>" => tilde(&p),
            "^" => caret(&p),
            _ => xrange(op, &p),
        })
    }

    /// Hyphen range "from - to".
    fn hyphen(from: &Part, to: &Part) -> Vec<Cmp> {
        let mut out = Vec::new();
        let pre_f: Vec<&str> = from.pre.iter().map(|s| s.as_str()).collect();
        let pre_t: Vec<&str> = to.pre.iter().map(|s| s.as_str()).collect();
        if let [Some(mj), mn, pt] = from.m {
            match (mn, pt) {
                (None, _) => out.push(bound(Op::Ge, mj, 0, 0, &[])),
                (Some(mi), None) => out.push(bound(Op::Ge, mj, mi, 0, &[])),
                (Some(mi), Some(pa)) => out.push(bound(Op::Ge, mj, mi, pa, &pre_f)),
            }
        }
        if let [Some(mj), mn, pt] = to.m {
            match (mn, pt) {
                (None, _) => out.push(lt_zero(mj + 1, 0, 0)),
                (Some(mi), None) => out.push(lt_zero(mj, mi + 1, 0)),
                (Some(mi), Some(pa)) => out.push(bound(Op::Le, mj, mi, pa, &pre_t)),
            }
        }
        out
    }

    /// One AND-set of comparators, e.g. ">=1.2.3 <2.0.0".
    fn parse_set(s: &str) -> Option<Vec<Cmp>> {
        const OPS: [&str; 8] = ["<=", ">=", "~>", "<", ">", "=", "~", "^"];
        let toks: Vec<&str> = s.split_whitespace().collect();
        if toks.is_empty() {
            return Some(vec![Cmp::Any]);
        }
        let mut out = Vec::new();
        let mut i = 0;
        while i < toks.len() {
            if i + 2 < toks.len() && toks[i + 1] == "-" {
                let from = parse_part(toks[i])?;
                let to = parse_part(toks[i + 2])?;
                out.extend(hyphen(&from, &to));
                i += 3;
            } else if OPS.contains(&toks[i]) && i + 1 < toks.len() {
                out.extend(comparator(&format!("{}{}", toks[i], toks[i + 1]))?);
                i += 2;
            } else {
                out.extend(comparator(toks[i])?);
                i += 1;
            }
        }
        if out.is_empty() {
            out.push(Cmp::Any);
        }
        Some(out)
    }

    /// A range is a "||" list of AND-sets.
    fn parse_range(s: &str) -> Option<Vec<Vec<Cmp>>> {
        s.split("||").map(|p| parse_set(p.trim())).collect()
    }

    fn cmp_ident(x: &str, y: &str) -> Ordering {
        match (is_num(x), is_num(y)) {
            (true, true) => x.len().cmp(&y.len()).then_with(|| x.cmp(y)),
            (true, false) => Ordering::Less,
            (false, true) => Ordering::Greater,
            (false, false) => x.cmp(y),
        }
    }

    pub fn cmp_ver(a: &Ver, b: &Ver) -> Ordering {
        let core = (a.major, a.minor, a.patch).cmp(&(b.major, b.minor, b.patch));
        if core != Ordering::Equal {
            return core;
        }
        match (a.pre.is_empty(), b.pre.is_empty()) {
            (true, true) => Ordering::Equal,
            (true, false) => Ordering::Greater,
            (false, true) => Ordering::Less,
            (false, false) => {
                for (x, y) in a.pre.iter().zip(b.pre.iter()) {
                    let o = cmp_ident(x, y);
                    if o != Ordering::Equal {
                        return o;
                    }
                }
                a.pre.len().cmp(&b.pre.len())
            }
        }
    }

    fn matches(c: &Cmp, v: &Ver) -> bool {
        match c {
            Cmp::Any => true,
            Cmp::Never => false,
            Cmp::Bound(op, b) => {
                let o = cmp_ver(v, b);
                match op {
                    Op::Lt => o == Ordering::Less,
                    Op::Le => o != Ordering::Greater,
                    Op::Gt => o == Ordering::Greater,
                    Op::Ge => o != Ordering::Less,
                    Op::Eq => o == Ordering::Equal,
                }
            }
        }
    }

    fn test_set(set: &[Cmp], v: &Ver) -> bool {
        if !set.iter().all(|c| matches(c, v)) {
            return false;
        }
        // A prerelease version only matches when a comparator in the same set names a
        // prerelease on the same major.minor.patch.
        if v.pre.is_empty() {
            return true;
        }
        set.iter().any(|c| match c {
            Cmp::Bound(_, b) => {
                !b.pre.is_empty() && b.major == v.major && b.minor == v.minor && b.patch == v.patch
            }
            _ => false,
        })
    }

    /// Equivalent of node-semver `satisfies(version, range)`. Invalid input gives false.
    pub fn satisfies(version: &str, range: &str) -> bool {
        let Some(v) = parse_version(version) else { return false };
        let Some(sets) = parse_range(range) else { return false };
        sets.iter().any(|set| test_set(set, &v))
    }
}

// ---------------------------------------------------------------- main

#[derive(Default)]
struct Totals {
    hours: f64,
    gross_raw: f64,
}

fn round2(x: f64) -> f64 {
    (x * 100.0).round() / 100.0
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).expect("failed to read stdin");
    let v: Value = serde_json::from_str(&input).expect("input is not valid JSON");

    // employee id -> (effective hourly rate, tax table)
    let mut employees: HashMap<String, (f64, i64)> = HashMap::new();
    let mut payslips: BTreeMap<String, Totals> = BTreeMap::new();
    for e in v["employees"].as_array().map(|a| a.as_slice()).unwrap_or(&[]) {
        let id = e["id"].as_str().unwrap_or_default().to_string();
        let mut hourly = e["hourly"].as_f64().unwrap_or(0.0);
        let table = e["table"].as_i64().unwrap_or(0);
        if semver::satisfies(e["contract"].as_str().unwrap_or_default(), RAISE_RANGE) {
            hourly *= 1.1;
        }
        employees.insert(id.clone(), (hourly, table));
        payslips.insert(id, Totals::default());
    }

    let holidays: HashSet<String> = v["holidays"]
        .as_array()
        .map(|a| a.iter().filter_map(|d| d.as_str().map(String::from)).collect())
        .unwrap_or_default();

    let month = v["month"].as_str().unwrap_or_default();
    let mut rejected: Vec<String> = Vec::new();
    for s in v["shifts"].as_array().map(|a| a.as_slice()).unwrap_or(&[]) {
        let date = s["date"].as_str().unwrap_or_default();
        // Shifts outside the payslip month are ignored: neither paid nor rejected.
        if date.get(..7) != Some(month) {
            continue;
        }
        let id = s["id"].as_str().unwrap_or_default().to_string();
        let emp_id = s["employee"].as_str().unwrap_or_default();
        let Some(&(hourly, _)) = employees.get(emp_id) else {
            rejected.push(id);
            continue;
        };
        let parsed = s["hours"].as_str().and_then(parse_hours).and_then(|h| {
            // An optional "break" is subtracted before rounding; a bad or too-long break rejects the shift.
            match s.get("break") {
                None | Some(Value::Null) => Some(h),
                Some(b) => {
                    let brk = b.as_str().and_then(parse_hours)?;
                    (brk <= h).then_some(h - brk)
                }
            }
        });
        let mult = if holidays.contains(date) {
            Some(holiday())
        } else {
            weekday_of(date).and_then(multiplier)
        };
        let (Some(parsed), Some(mult)) = (parsed, mult) else {
            rejected.push(id);
            continue;
        };
        let hours = round_up(parsed);
        let t = payslips.get_mut(emp_id).expect("employee present");
        t.hours += hours;
        t.gross_raw += hours * hourly * mult;
    }
    rejected.sort();

    let mut out = serde_json::Map::new();
    for (id, t) in &payslips {
        let (_, table) = employees[id];
        let gross = round2(t.gross_raw);
        let tax = withholding(gross, table);
        let net = round2(gross - tax as f64);
        // Employer-paid pension: does not change tax or net.
        let pension = round2(gross * PENSION_RATE);
        out.insert(
            id.clone(),
            json!({ "hours": t.hours, "gross": gross, "tax": tax, "net": net, "pension": pension }),
        );
    }

    let result = json!({ "payslips": Value::Object(out), "rejected": rejected });
    println!("{}", serde_json::to_string(&result).expect("serialize"));
}
