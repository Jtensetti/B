use std::collections::BTreeMap;
use std::io::{self, Read};

use serde::{Deserialize, Serialize};

// Ports of the libraries in libs/ (Go tariff, C# Tax, Python calendar, npm
// fastest-levenshtein). The road distance comes from the geo crate directly.

// ---- tariff (libs/tariff/tariff.go) ----

fn tariff_zone(country: &str) -> Option<u8> {
    let c = country.trim().to_uppercase();
    match c.as_str() {
        "SE" => Some(1),
        "NO" | "DK" | "FI" => Some(2),
        "DE" | "NL" | "PL" => Some(3),
        "FR" | "ES" | "IT" => Some(4),
        _ => None,
    }
}

fn tariff_base_price(zone: u8, weight_kg: f64) -> f64 {
    let (start, per_kg) = match zone {
        1 => (49.0, 6.5),
        2 => (79.0, 9.0),
        3 => (99.0, 11.0),
        _ => (129.0, 14.5),
    };
    let billed = (weight_kg * 2.0).ceil() / 2.0;
    start + per_kg * billed
}

// ---- Tax (libs/Tax/Vat.cs) ----

fn vat_rate(country: &str) -> Option<f64> {
    let c = country.trim().to_uppercase();
    Some(match c.as_str() {
        "SE" => 0.25,
        "NO" => 0.25,
        "DK" => 0.25,
        "FI" => 0.255,
        "DE" => 0.19,
        "NL" => 0.21,
        "PL" => 0.23,
        "FR" => 0.20,
        "ES" => 0.21,
        "IT" => 0.22,
        _ => return None,
    })
}

fn vat_reverse_charge(country: &str, business: bool) -> bool {
    let c = country.trim().to_uppercase();
    let eu = matches!(c.as_str(), "SE" | "DK" | "FI" | "DE" | "NL" | "PL" | "FR" | "ES" | "IT");
    business && c != "SE" && eu
}

// ---- calendar (libs/calendar/workdays.py) ----

const HOLIDAYS_2026: &[&str] = &[
    "2026-01-01", "2026-01-06", "2026-04-03", "2026-04-06", "2026-05-01", "2026-05-14",
    "2026-06-06", "2026-06-19", "2026-12-24", "2026-12-25", "2026-12-26", "2026-12-31",
];

/// Days since 1970-01-01 for a proleptic Gregorian date.
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = (if y >= 0 { y } else { y - 399 }) / 400;
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

/// (year, month, day) from days since 1970-01-01.
fn civil_from_days(z: i64) -> (i64, i64, i64) {
    let z = z + 719468;
    let era = (if z >= 0 { z } else { z - 146096 }) / 146097;
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (if m <= 2 { y + 1 } else { y }, m, d)
}

fn parse_iso(s: &str) -> Option<i64> {
    let b = s.as_bytes();
    if b.len() != 10 || b[4] != b'-' || b[7] != b'-' {
        return None;
    }
    let y: i64 = s[0..4].parse().ok()?;
    let m: i64 = s[5..7].parse().ok()?;
    let d: i64 = s[8..10].parse().ok()?;
    if !(1..=12).contains(&m) || d < 1 {
        return None;
    }
    let leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
    let dim = match m {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        _ => {
            if leap {
                29
            } else {
                28
            }
        }
    };
    if d > dim {
        return None;
    }
    Some(days_from_civil(y, m, d))
}

fn format_iso(days: i64) -> String {
    let (y, m, d) = civil_from_days(days);
    format!("{:04}-{:02}-{:02}", y, m, d)
}

fn is_workday_days(days: i64) -> bool {
    // 1970-01-01 was a Thursday; weekday Monday=0 .. Sunday=6.
    let weekday = (days + 3).rem_euclid(7);
    weekday < 5 && !HOLIDAYS_2026.contains(&format_iso(days).as_str())
}

fn is_workday_iso(iso: &str) -> bool {
    parse_iso(iso).map_or(false, is_workday_days)
}

fn next_workday(iso: &str) -> Option<String> {
    let mut d = parse_iso(iso)? + 1;
    while !is_workday_days(d) {
        d += 1;
    }
    Some(format_iso(d))
}

// ---- fastest-levenshtein (libs/node_modules) ----

fn distance(a: &str, b: &str) -> usize {
    let a: Vec<u16> = a.encode_utf16().collect();
    let b: Vec<u16> = b.encode_utf16().collect();
    if a.is_empty() {
        return b.len();
    }
    if b.is_empty() {
        return a.len();
    }
    let mut row: Vec<usize> = (0..=a.len()).collect();
    for i in 1..=b.len() {
        let mut prev = i;
        for j in 1..=a.len() {
            let val = if b[i - 1] == a[j - 1] {
                row[j - 1]
            } else {
                (row[j - 1] + 1).min(prev + 1).min(row[j] + 1)
            };
            row[j - 1] = prev;
            prev = val;
        }
        row[a.len()] = prev;
    }
    row[a.len()]
}

// ---- program ----

#[derive(Deserialize)]
struct Depot {
    lat: f64,
    lon: f64,
}

#[derive(Deserialize)]
struct Order {
    id: String,
    product: String,
    country: String,
    lat: f64,
    lon: f64,
    date: String,
    business: bool,
    #[serde(default)]
    qty: Option<f64>,
    #[serde(default)]
    express: Option<bool>,
}

#[derive(Deserialize)]
struct Input {
    depot: Depot,
    catalog: BTreeMap<String, f64>,
    orders: Vec<Order>,
    #[serde(default)]
    rates: BTreeMap<String, f64>,
}

#[derive(Serialize)]
struct Quote {
    price: f64,
    delivery: String,
    currency: String,
}

#[derive(Serialize)]
struct Output {
    quotes: BTreeMap<String, Quote>,
    unknown: Vec<String>,
}

/// Catalog name closest to the ordered name (distance <= 2), ties to the alphabetically first.
fn match_product<'a>(catalog: &'a BTreeMap<String, f64>, product: &str) -> Option<(&'a String, f64)> {
    let mut best: Option<(usize, &String, f64)> = None;
    // BTreeMap iterates in alphabetical order, so the first minimum wins ties.
    for (name, weight) in catalog {
        let d = distance(product, name);
        match best {
            Some((bd, _, _)) if bd <= d => {}
            _ => best = Some((d, name, *weight)),
        }
    }
    match best {
        Some((d, name, w)) if d <= 2 => Some((name, w)),
        _ => None,
    }
}

fn round2(x: f64) -> f64 {
    (x * 100.0).round() / 100.0
}

fn quote_order(
    depot: &Depot,
    catalog: &BTreeMap<String, f64>,
    rates: &BTreeMap<String, f64>,
    o: &Order,
) -> Option<Quote> {
    let (_, unit_weight) = match_product(catalog, &o.product)?;
    let weight = unit_weight * o.qty.unwrap_or(1.0);
    let zone = tariff_zone(&o.country)?;
    let road = geo::road_km(depot.lat, depot.lon, o.lat, o.lon);
    let surcharge = ((road - 300.0).max(0.0) * 0.80).min(400.0);
    let express = o.express.unwrap_or(false);
    let mut base = if o.business && weight >= 50.0 {
        0.0
    } else {
        tariff_base_price(zone, weight)
    };
    if express {
        base *= 1.5;
    }
    let net = base + surcharge;
    let vat = if vat_reverse_charge(&o.country, o.business) {
        0.0
    } else {
        vat_rate(&o.country)?
    };
    let sek = round2(net * (1.0 + vat));
    let delivery = if express && is_workday_iso(&o.date) {
        o.date.clone()
    } else {
        next_workday(&o.date)?
    };
    let (price, currency) = if o.country.trim().to_uppercase() == "SE" {
        (sek, "SEK")
    } else {
        let rate = *rates.get("EUR")?;
        (round2(sek / rate), "EUR")
    };
    Some(Quote {
        price,
        delivery,
        currency: currency.to_string(),
    })
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).expect("read stdin");
    let input: Input = serde_json::from_str(&input).expect("valid input JSON");

    let mut quotes = BTreeMap::new();
    let mut unknown = Vec::new();
    for o in &input.orders {
        match quote_order(&input.depot, &input.catalog, &input.rates, o) {
            Some(q) => {
                quotes.insert(o.id.clone(), q);
            }
            None => unknown.push(o.id.clone()),
        }
    }
    unknown.sort();

    let out = Output { quotes, unknown };
    println!("{}", serde_json::to_string(&out).expect("serialize"));
}
