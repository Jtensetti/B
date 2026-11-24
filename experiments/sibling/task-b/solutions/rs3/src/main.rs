use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, HashMap};
use std::io::{self, Read};

/// Port of libs/hours (Go): reads "H:MM" and returns hours.
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

/// Multiplier from libs/Rules (C#): Mon-Fri 1.0, Sat 1.5, Sun 2.0.
/// `weekday` is 0 for Monday through 6 for Sunday.
fn overtime_multiplier(weekday: usize) -> f64 {
    match weekday {
        5 => 1.5,
        6 => 2.0,
        _ => 1.0,
    }
}

/// Weekday (0 = Monday .. 6 = Sunday) of a "YYYY-MM-DD" date, or None if malformed.
fn weekday_of(date: &str) -> Option<usize> {
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
    // Sakamoto's algorithm: 0 = Sunday .. 6 = Saturday.
    const T: [i64; 12] = [0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4];
    if m < 3 {
        y -= 1;
    }
    let s = (y + y / 4 - y / 100 + y / 400 + T[(m - 1) as usize] + d) % 7;
    // Convert to 0 = Monday.
    Some(((s + 6) % 7) as usize)
}

/// True when a contract version satisfies ">=3.0.0" as npm semver decides:
/// the version must be a valid semver, major >= 3, and must not be a prerelease.
fn satisfies_senior(version: &str) -> bool {
    let mut v = version.trim();
    if let Some(rest) = v.strip_prefix('=') {
        v = rest;
    }
    if let Some(rest) = v.strip_prefix('v') {
        v = rest;
    }
    // Build metadata does not affect precedence.
    let v = v.split('+').next().unwrap_or("");
    let (core, pre) = match v.split_once('-') {
        Some((c, p)) => (c, Some(p)),
        None => (v, None),
    };
    if pre.is_some() {
        return false;
    }
    let parts: Vec<&str> = core.split('.').collect();
    if parts.len() != 3 {
        return false;
    }
    let mut nums = [0u64; 3];
    for (i, p) in parts.iter().enumerate() {
        if p.is_empty() || !p.bytes().all(|b| b.is_ascii_digit()) || (p.len() > 1 && p.starts_with('0')) {
            return false;
        }
        match p.parse::<u64>() {
            Ok(n) => nums[i] = n,
            Err(_) => return false,
        }
    }
    nums[0] >= 3
}

/// Port of Overtime.Holiday() from libs/Rules: multiplier for a public holiday.
const HOLIDAY_MULTIPLIER: f64 = 2.0;

/// Port of libs/quarter (Rust): rounds hours up to the next quarter hour.
fn round_up(hours: f64) -> f64 {
    quarter::round_up(hours)
}

/// Port of libs/payroll (Python): tax to withhold in whole kronor.
fn withholding(gross: f64, table: i64) -> i64 {
    let rate = table as f64 / 100.0;
    let taxable = (gross - 2000.0).max(0.0);
    let low = taxable.min(48000.0) * rate;
    let high = (gross - 50000.0).max(0.0) * (rate + 0.20);
    (low + high).floor() as i64
}

fn round2(x: f64) -> f64 {
    (x * 100.0).round() / 100.0
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).expect("read stdin");
    let root: Value = serde_json::from_str(input.trim()).expect("valid JSON input");

    // employee id -> (hourly, table)
    let mut employees: HashMap<String, (f64, i64)> = HashMap::new();
    let mut order: Vec<String> = Vec::new();
    for e in root["employees"].as_array().map(|v| v.as_slice()).unwrap_or(&[]) {
        let id = e["id"].as_str().unwrap_or("").to_string();
        let mut hourly = e["hourly"].as_f64().unwrap_or(0.0);
        let table = e["table"].as_i64().unwrap_or(0);
        if satisfies_senior(e["contract"].as_str().unwrap_or("")) {
            hourly *= 1.1;
        }
        if !employees.contains_key(&id) {
            order.push(id.clone());
        }
        employees.insert(id, (hourly, table));
    }

    // per employee: total hours, gross (unrounded sum)
    let mut total_hours: HashMap<String, f64> = HashMap::new();
    let mut total_pay: HashMap<String, f64> = HashMap::new();
    let mut rejected: Vec<String> = Vec::new();
    let month = root["month"].as_str().unwrap_or("").to_string();
    let holidays: Vec<String> = root["holidays"]
        .as_array()
        .map(|v| v.iter().filter_map(|d| d.as_str().map(String::from)).collect())
        .unwrap_or_default();

    for s in root["shifts"].as_array().map(|v| v.as_slice()).unwrap_or(&[]) {
        let sid = s["id"].as_str().unwrap_or("").to_string();
        let emp = s["employee"].as_str().unwrap_or("");
        let date = s["date"].as_str().unwrap_or("");
        let raw = s["hours"].as_str().unwrap_or("");

        // Shifts outside the payroll month are ignored, neither paid nor rejected.
        if date.get(..7) != Some(month.as_str()) {
            continue;
        }

        let Some(&(hourly, _table)) = employees.get(emp) else {
            rejected.push(sid);
            continue;
        };
        let Some(mut parsed) = parse_hours(raw) else {
            rejected.push(sid);
            continue;
        };
        // An optional break is subtracted from the worked time.
        if let Some(brk) = s.get("break").filter(|b| !b.is_null()) {
            let brk = brk.as_str().and_then(parse_hours);
            match brk {
                Some(b) if b <= parsed => parsed -= b,
                _ => {
                    rejected.push(sid);
                    continue;
                }
            }
        }
        let Some(wd) = weekday_of(date) else {
            rejected.push(sid);
            continue;
        };

        let hours = round_up(parsed);
        // Public holidays pay the holiday multiplier whatever the weekday.
        let multiplier = if holidays.iter().any(|h| h == date) {
            HOLIDAY_MULTIPLIER
        } else {
            overtime_multiplier(wd)
        };
        let pay = hours * hourly * multiplier;
        *total_hours.entry(emp.to_string()).or_insert(0.0) += hours;
        *total_pay.entry(emp.to_string()).or_insert(0.0) += pay;
    }

    let mut payslips: BTreeMap<String, Value> = BTreeMap::new();
    for id in &order {
        let (_, table) = employees[id];
        let hours = total_hours.get(id).copied().unwrap_or(0.0);
        let gross = round2(total_pay.get(id).copied().unwrap_or(0.0));
        let tax = withholding(gross, table);
        let net = gross - tax as f64;
        // Employer-paid pension: 4.5 % of gross, rounded half up to 2 decimals (done in whole öre).
        let gross_cents = (gross * 100.0).round() as i64;
        let pension = ((gross_cents * 45 + 500) / 1000) as f64 / 100.0;
        payslips.insert(
            id.clone(),
            json!({ "hours": hours, "gross": gross, "tax": tax, "net": net, "pension": pension }),
        );
    }

    rejected.sort();
    let mut out = Map::new();
    out.insert(
        "payslips".to_string(),
        Value::Object(payslips.into_iter().collect()),
    );
    out.insert("rejected".to_string(), json!(rejected));
    println!("{}", Value::Object(out));
}
