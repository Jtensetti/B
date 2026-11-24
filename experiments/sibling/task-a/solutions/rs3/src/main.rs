use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
use std::io::{self, Read};

// ---------- libs/geo (Rust, used directly) ----------
// road_km comes from the geo crate.

// ---------- libs/tariff (Go) ported ----------
fn tariff_zone(country: &str) -> Option<i32> {
    let c = country.trim().to_uppercase();
    match c.as_str() {
        "SE" => Some(1),
        "NO" | "DK" | "FI" => Some(2),
        "DE" | "NL" | "PL" => Some(3),
        "FR" | "ES" | "IT" => Some(4),
        _ => None,
    }
}

fn tariff_base_price(zone: i32, weight_kg: f64) -> f64 {
    let (start, per_kg) = match zone {
        1 => (49.0, 6.5),
        2 => (79.0, 9.0),
        3 => (99.0, 11.0),
        _ => (129.0, 14.5),
    };
    let billed = (weight_kg * 2.0).ceil() / 2.0;
    start + per_kg * billed
}

// ---------- libs/Tax (C#) ported ----------
fn vat_rate(country: &str) -> Option<f64> {
    let c = country.trim().to_uppercase();
    match c.as_str() {
        "SE" | "NO" | "DK" => Some(0.25),
        "FI" => Some(0.255),
        "DE" => Some(0.19),
        "NL" => Some(0.21),
        "PL" => Some(0.23),
        "FR" => Some(0.20),
        "ES" => Some(0.21),
        "IT" => Some(0.22),
        _ => None,
    }
}

fn vat_reverse_charge(country: &str, business: bool) -> bool {
    let c = country.trim().to_uppercase();
    let eu = ["SE", "DK", "FI", "DE", "NL", "PL", "FR", "ES", "IT"];
    business && c != "SE" && eu.contains(&c.as_str())
}

// ---------- libs/calendar (Python) ported ----------
const HOLIDAYS_2026: [&str; 12] = [
    "2026-01-01", "2026-01-06", "2026-04-03", "2026-04-06", "2026-05-01", "2026-05-14",
    "2026-06-06", "2026-06-19", "2026-12-24", "2026-12-25", "2026-12-26", "2026-12-31",
];

/// Days since 1970-01-01 for a proleptic Gregorian date.
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

/// Inverse of days_from_civil.
fn civil_from_days(z: i64) -> (i64, i64, i64) {
    let z = z + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (if m <= 2 { y + 1 } else { y }, m, d)
}

fn parse_iso(s: &str) -> Option<(i64, i64, i64)> {
    let b = s.as_bytes();
    if b.len() != 10 || b[4] != b'-' || b[7] != b'-' {
        return None;
    }
    let y: i64 = s[0..4].parse().ok()?;
    let m: i64 = s[5..7].parse().ok()?;
    let d: i64 = s[8..10].parse().ok()?;
    if !(1..=12).contains(&m) || d < 1 || d > days_in_month(y, m) {
        return None;
    }
    Some((y, m, d))
}

fn days_in_month(y: i64, m: i64) -> i64 {
    match m {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        _ => {
            if (y % 4 == 0 && y % 100 != 0) || y % 400 == 0 {
                29
            } else {
                28
            }
        }
    }
}

fn fmt_iso(y: i64, m: i64, d: i64) -> String {
    format!("{:04}-{:02}-{:02}", y, m, d)
}

/// Weekday with Monday = 0 (1970-01-01 was a Thursday, index 3).
fn weekday(days: i64) -> i64 {
    (days + 3).rem_euclid(7)
}

fn is_workday_days(days: i64) -> bool {
    let (y, m, d) = civil_from_days(days);
    weekday(days) < 5 && !HOLIDAYS_2026.contains(&fmt_iso(y, m, d).as_str())
}

fn next_workday(iso: &str) -> Option<String> {
    let (y, m, d) = parse_iso(iso)?;
    let mut day = days_from_civil(y, m, d) + 1;
    while !is_workday_days(day) {
        day += 1;
    }
    let (y, m, d) = civil_from_days(day);
    Some(fmt_iso(y, m, d))
}

// ---------- fastest-levenshtein (JS) ported: standard edit distance over UTF-16 units ----------
fn levenshtein(a: &str, b: &str) -> usize {
    let a: Vec<u16> = a.encode_utf16().collect();
    let b: Vec<u16> = b.encode_utf16().collect();
    if a.is_empty() {
        return b.len();
    }
    if b.is_empty() {
        return a.len();
    }
    let mut prev: Vec<usize> = (0..=b.len()).collect();
    let mut cur = vec![0usize; b.len() + 1];
    for i in 1..=a.len() {
        cur[0] = i;
        for j in 1..=b.len() {
            let cost = if a[i - 1] == b[j - 1] { 0 } else { 1 };
            cur[j] = (prev[j] + 1).min(cur[j - 1] + 1).min(prev[j - 1] + cost);
        }
        std::mem::swap(&mut prev, &mut cur);
    }
    prev[b.len()]
}

/// Resolve an ordered product name against the catalog, or None when unknown.
fn resolve_product<'a>(name: &str, catalog: &'a BTreeMap<String, f64>) -> Option<&'a String> {
    let mut best: Option<(usize, &String)> = None;
    // BTreeMap iterates in sorted order, so the first name at the minimum distance wins ties.
    for cand in catalog.keys() {
        let d = levenshtein(name, cand);
        match best {
            Some((bd, _)) if d >= bd => {}
            _ => best = Some((d, cand)),
        }
    }
    match best {
        Some((d, cand)) if d <= 2 => Some(cand),
        _ => None,
    }
}

fn round2(x: f64) -> f64 {
    (x * 100.0).round() / 100.0
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).expect("read stdin");
    let v: Value = serde_json::from_str(&input).expect("valid JSON input");

    let depot_lat = v["depot"]["lat"].as_f64().unwrap_or(0.0);
    let depot_lon = v["depot"]["lon"].as_f64().unwrap_or(0.0);

    let mut catalog: BTreeMap<String, f64> = BTreeMap::new();
    if let Some(obj) = v["catalog"].as_object() {
        for (name, w) in obj {
            catalog.insert(name.clone(), w.as_f64().unwrap_or(0.0));
        }
    }

    let eur_rate = v["rates"]["EUR"].as_f64().unwrap_or(0.0);

    let mut quotes = Map::new();
    let mut unknown: Vec<String> = Vec::new();

    let orders = v["orders"].as_array().cloned().unwrap_or_default();
    for o in &orders {
        let id = o["id"].as_str().unwrap_or("").to_string();
        let product = o["product"].as_str().unwrap_or("");
        let country = o["country"].as_str().unwrap_or("");
        let lat = o["lat"].as_f64().unwrap_or(0.0);
        let lon = o["lon"].as_f64().unwrap_or(0.0);
        let date = o["date"].as_str().unwrap_or("");
        let business = o["business"].as_bool().unwrap_or(false);
        let qty = o["qty"].as_f64().unwrap_or(1.0);
        let express = o["express"].as_bool().unwrap_or(false);

        let weight = match resolve_product(product, &catalog) {
            Some(name) => catalog[name] * qty,
            None => {
                unknown.push(id);
                continue;
            }
        };
        let zone = match tariff_zone(country) {
            Some(z) => z,
            None => {
                unknown.push(id);
                continue;
            }
        };
        let rate = match vat_rate(country) {
            Some(r) => r,
            None => {
                unknown.push(id);
                continue;
            }
        };
        let same_day = express && parse_iso(date).map_or(false, |(y, m, d)| is_workday_days(days_from_civil(y, m, d)));
        let delivery = match if same_day { Some(date.to_string()) } else { next_workday(date) } {
            Some(d) => d,
            None => {
                unknown.push(id);
                continue;
            }
        };

        let mut base = if business && weight >= 50.0 {
            0.0
        } else {
            tariff_base_price(zone, weight)
        };
        if express {
            base *= 1.5;
        }
        let road = geo::road_km(depot_lat, depot_lon, lat, lon);
        let extra = if road > 300.0 { ((road - 300.0) * 0.80).min(400.0) } else { 0.0 };
        let net = base + extra;
        let vat = if vat_reverse_charge(country, business) { 0.0 } else { rate };
        let sek = round2(net * (1.0 + vat));
        let (price, currency) = if country.trim().to_uppercase() == "SE" {
            (sek, "SEK")
        } else {
            if eur_rate <= 0.0 {
                unknown.push(id);
                continue;
            }
            (round2(sek / eur_rate), "EUR")
        };

        quotes.insert(id, json!({ "price": price, "currency": currency, "delivery": delivery }));
    }

    unknown.sort();
    let out = json!({ "quotes": Value::Object(quotes), "unknown": unknown });
    println!("{}", out);
}
