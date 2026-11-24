// Delivery quotes for a furniture shop in Stockholm.
//
// The behaviour of the libraries in libs/ is ported here, because the program
// must run with `cargo run` alone:
//   - libs/tariff  (Go)     -> zone(), base_price()
//   - libs/geo     (Rust)   -> road_km()
//   - libs/Tax     (C#)     -> vat_rate(), reverse_charge()
//   - libs/calendar (Python)-> next_workday()
//   - fastest-levenshtein   -> levenshtein(), closest_product()

use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashSet};
use std::io::{self, Read};

#[derive(Deserialize)]
struct Input {
    depot: Point,
    catalog: BTreeMap<String, f64>,
    rates: BTreeMap<String, f64>,
    orders: Vec<Order>,
}

#[derive(Deserialize)]
struct Point {
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
    // Optional quantity, default 1. The parcel weighs qty times the catalog weight.
    #[serde(default)]
    qty: Option<f64>,
    // Express orders: base price times 1.5, delivered on the order date if it is a working day.
    #[serde(default)]
    express: bool,
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

// ---------- libs/tariff (Go) ----------

fn zone(country: &str) -> Option<u32> {
    match country.trim().to_uppercase().as_str() {
        "SE" => Some(1),
        "NO" | "DK" | "FI" => Some(2),
        "DE" | "NL" | "PL" => Some(3),
        "FR" | "ES" | "IT" => Some(4),
        _ => None,
    }
}

// Start and per-kg price in SEK excluding VAT, indexed by zone 1..=4.
fn base_price(zone: u32, weight_kg: f64) -> f64 {
    let (start, per_kg) = match zone {
        1 => (49.0, 6.5),
        2 => (79.0, 9.0),
        3 => (99.0, 11.0),
        _ => (129.0, 14.5),
    };
    // Weight is rounded up to the next half kilogram.
    let billed = (weight_kg * 2.0).ceil() / 2.0;
    start + per_kg * billed
}

// ---------- libs/geo (Rust) ----------

const EARTH_RADIUS_KM: f64 = 6371.0;

fn distance_km(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    let (p1, p2) = (lat1.to_radians(), lat2.to_radians());
    let dp = (lat2 - lat1).to_radians();
    let dl = (lon2 - lon1).to_radians();
    let a = (dp / 2.0).sin().powi(2) + p1.cos() * p2.cos() * (dl / 2.0).sin().powi(2);
    2.0 * EARTH_RADIUS_KM * a.sqrt().asin()
}

// Road distance estimate: great-circle distance times 1.25.
fn road_km(lat1: f64, lon1: f64, lat2: f64, lon2: f64) -> f64 {
    distance_km(lat1, lon1, lat2, lon2) * 1.25
}

// ---------- libs/Tax (C#) ----------

fn vat_rate(country: &str) -> Option<f64> {
    match country.trim().to_uppercase().as_str() {
        "SE" | "NO" | "DK" => Some(0.25),
        "FI" => Some(0.255),
        "DE" => Some(0.19),
        "NL" | "ES" => Some(0.21),
        "PL" => Some(0.23),
        "FR" => Some(0.20),
        "IT" => Some(0.22),
        _ => None,
    }
}

// True when a business customer in another EU country pays no VAT.
fn reverse_charge(country: &str, business: bool) -> bool {
    let c = country.trim().to_uppercase();
    const EU: [&str; 9] = ["SE", "DK", "FI", "DE", "NL", "PL", "FR", "ES", "IT"];
    business && c != "SE" && EU.contains(&c.as_str())
}

// ---------- libs/calendar (Python) ----------

// Civil date <-> day number (days since 1970-01-01), proleptic Gregorian.
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

fn civil_from_days(z: i64) -> (i64, i64, i64) {
    let z = z + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (if m <= 2 { y + 1 } else { y }, m, d)
}

fn parse_date(iso: &str) -> (i64, i64, i64) {
    let mut it = iso.split('-').map(|p| p.trim().parse::<i64>().unwrap_or(0));
    (
        it.next().unwrap_or(1970),
        it.next().unwrap_or(1),
        it.next().unwrap_or(1),
    )
}

fn format_date(days: i64) -> String {
    let (y, m, d) = civil_from_days(days);
    format!("{:04}-{:02}-{:02}", y, m, d)
}

// Swedish public holidays in 2026 (ISO dates), as in the calendar library.
const HOLIDAYS_2026: [&str; 12] = [
    "2026-01-01", "2026-01-06", "2026-04-03", "2026-04-06", "2026-05-01", "2026-05-14",
    "2026-06-06", "2026-06-19", "2026-12-24", "2026-12-25", "2026-12-26", "2026-12-31",
];

fn is_workday_days(days: i64, holidays: &HashSet<&str>) -> bool {
    // 1970-01-01 was a Thursday; Monday = 0 as in Python.
    let weekday = (days + 3).rem_euclid(7);
    weekday < 5 && !holidays.contains(format_date(days).as_str())
}

// True for a Monday to Friday that is not a Swedish public holiday.
fn is_workday(iso: &str) -> bool {
    let holidays: HashSet<&str> = HOLIDAYS_2026.iter().copied().collect();
    let (y, m, d) = parse_date(iso);
    is_workday_days(days_from_civil(y, m, d), &holidays)
}

// The first working day strictly after the given date.
fn next_workday(iso: &str) -> String {
    let holidays: HashSet<&str> = HOLIDAYS_2026.iter().copied().collect();
    let (y, m, d) = parse_date(iso);
    let mut day = days_from_civil(y, m, d) + 1;
    while !is_workday_days(day, &holidays) {
        day += 1;
    }
    format_date(day)
}

// ---------- fastest-levenshtein ----------

fn levenshtein(a: &str, b: &str) -> usize {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    if a.is_empty() {
        return b.len();
    }
    if b.is_empty() {
        return a.len();
    }
    let mut prev: Vec<usize> = (0..=b.len()).collect();
    let mut cur = vec![0usize; b.len() + 1];
    for (i, ca) in a.iter().enumerate() {
        cur[0] = i + 1;
        for (j, cb) in b.iter().enumerate() {
            let cost = if ca == cb { 0 } else { 1 };
            cur[j + 1] = (prev[j] + cost).min(prev[j + 1] + 1).min(cur[j] + 1);
        }
        std::mem::swap(&mut prev, &mut cur);
    }
    prev[b.len()]
}

// The catalog name closest to the ordered name, if within distance 2.
// Ties go to the alphabetically first name (the catalog is a BTreeMap).
fn closest_product<'a>(name: &str, catalog: &'a BTreeMap<String, f64>) -> Option<&'a str> {
    let mut best: Option<(usize, &str)> = None;
    for candidate in catalog.keys() {
        let d = levenshtein(name, candidate);
        match best {
            Some((bd, _)) if d >= bd => {}
            _ => best = Some((d, candidate.as_str())),
        }
    }
    match best {
        Some((d, n)) if d <= 2 => Some(n),
        _ => None,
    }
}

// ---------- quoting ----------

fn quote(input: &Input, o: &Order) -> Option<Quote> {
    let product = closest_product(&o.product, &input.catalog)?;
    let qty = o.qty.unwrap_or(1.0);
    let weight = *input.catalog.get(product)? * qty;
    let zone = zone(&o.country)?;
    let vat = if reverse_charge(&o.country, o.business) {
        0.0
    } else {
        vat_rate(&o.country)?
    };

    let road = road_km(input.depot.lat, input.depot.lon, o.lat, o.lon);
    // Distance surcharge: 0.80 SEK per road km beyond 300 km, capped at 400 SEK per order.
    let surcharge = (0.80 * (road - 300.0).max(0.0)).min(400.0);
    // Free freight: business parcels of 50 kg or more have no base price.
    let mut base = if o.business && weight >= 50.0 {
        0.0
    } else {
        base_price(zone, weight)
    };
    let delivery = if o.express {
        base *= 1.5;
        if is_workday(&o.date) {
            o.date.clone()
        } else {
            next_workday(&o.date)
        }
    } else {
        next_workday(&o.date)
    };
    let net = base + surcharge;
    let sek = ((net * (1.0 + vat)) * 100.0).round() / 100.0;

    // Customers outside Sweden pay in euros at the rate given in the input (SEK per EUR).
    let (price, currency) = if o.country.trim().to_uppercase() == "SE" {
        (sek, "SEK")
    } else {
        let eur = input.rates.get("EUR")?;
        (((sek / eur) * 100.0).round() / 100.0, "EUR")
    };

    Some(Quote {
        price,
        delivery,
        currency: currency.to_string(),
    })
}

fn main() {
    let mut raw = String::new();
    io::stdin()
        .read_to_string(&mut raw)
        .expect("failed to read standard input");
    let input: Input = serde_json::from_str(&raw).expect("invalid input JSON");

    let mut quotes = BTreeMap::new();
    let mut unknown = Vec::new();
    for o in &input.orders {
        match quote(&input, o) {
            Some(q) => {
                quotes.insert(o.id.clone(), q);
            }
            None => unknown.push(o.id.clone()),
        }
    }
    unknown.sort();

    let out = Output { quotes, unknown };
    println!(
        "{}",
        serde_json::to_string(&out).expect("failed to serialise output")
    );
}
