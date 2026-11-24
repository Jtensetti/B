// Reorder suggestions for a furniture warehouse.
//
// Ports of the workspace libraries that are not Rust:
// - leadtime (Go, libs/leadtime/leadtime.go): Days(supplier)
// - Packaging (C#, libs/Packaging/Packs.cs): RoundUp(quantity, packSize)
// - weeks (Python, libs/weeks/dates.py): add_days(iso_date, days)
// The Rust `stats` crate (libs/stats) is used directly.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::io::{self, Read};

#[derive(Deserialize)]
struct Input {
    today: String,
    items: Vec<Item>,
    sales: Vec<Sale>,
}

#[derive(Deserialize)]
struct Item {
    sku: String,
    supplier: String,
    stock: i64,
    pack: i64,
    price: f64,
}

#[derive(Deserialize)]
struct Sale {
    sku: String,
    date: String,
    qty: i64,
}

#[derive(Serialize)]
struct Order {
    qty: i64,
    arrive: String,
}

#[derive(Serialize)]
struct Output {
    orders: BTreeMap<String, Order>,
    unknown: Vec<String>,
}

// --- leadtime (libs/leadtime/leadtime.go) ---
fn lead_days(supplier: &str) -> Option<i64> {
    match supplier {
        "Nordic Timber" => Some(12),
        "Baltic Steel" => Some(9),
        "Lumo Lighting" => Some(5),
        "Fabrikk AS" => Some(7),
        "Textil Partner" => Some(14),
        _ => None,
    }
}

// Known supplier names, sorted as leadtime.Suppliers() lists them.
const SUPPLIERS: [&str; 5] = ["Baltic Steel", "Fabrikk AS", "Lumo Lighting", "Nordic Timber", "Textil Partner"];

// Levenshtein distance over UTF-16 code units, as fastest-levenshtein's distance().
fn levenshtein(a: &str, b: &str) -> usize {
    let a: Vec<u16> = a.encode_utf16().collect();
    let b: Vec<u16> = b.encode_utf16().collect();
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

// Closest known supplier within distance 2; ties go to the alphabetically first name.
fn resolve_supplier(name: &str) -> Option<&'static str> {
    let mut best: Option<(usize, &'static str)> = None;
    for &known in SUPPLIERS.iter() {
        let d = levenshtein(name, known);
        if best.map_or(true, |(bd, _)| d < bd) {
            best = Some((d, known));
        }
    }
    best.filter(|(d, _)| *d <= 2).map(|(_, n)| n)
}

// --- Packaging (libs/Packaging/Packs.cs) ---
fn round_up(quantity: i64, pack_size: i64) -> i64 {
    if pack_size <= 0 {
        panic!("pack size must be positive");
    }
    if quantity <= 0 {
        return 0;
    }
    (quantity + pack_size - 1) / pack_size * pack_size
}

// --- calendar helpers (libs/weeks/dates.py), proleptic Gregorian day numbers ---
fn days_from_civil(y: i64, m: i64, d: i64) -> i64 {
    let y = if m <= 2 { y - 1 } else { y };
    let era = (if y >= 0 { y } else { y - 399 }) / 400;
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146097 + doe - 719468
}

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

fn parse_day(iso: &str) -> i64 {
    let mut it = iso.split('-').map(|p| p.parse::<i64>().expect("bad date"));
    let (y, m, d) = (
        it.next().expect("bad date"),
        it.next().expect("bad date"),
        it.next().expect("bad date"),
    );
    days_from_civil(y, m, d)
}

// ISO week number (1-53), as weeks::iso_week. Monday-based weekday; 1970-01-01 was a Thursday.
fn iso_week(z: i64) -> i64 {
    let weekday = (z + 3).rem_euclid(7); // Monday = 0
    let thursday = z - weekday + 3;
    let (year, _, _) = civil_from_days(thursday);
    (thursday - days_from_civil(year, 1, 1)) / 7 + 1
}

// weeks::to_weekday: the date itself on Monday to Friday, else the following Monday.
fn to_weekday(z: i64) -> i64 {
    let mut d = z;
    while (d + 3).rem_euclid(7) >= 5 {
        d += 1;
    }
    d
}

fn format_day(z: i64) -> String {
    let (y, m, d) = civil_from_days(z);
    format!("{:04}-{:02}-{:02}", y, m, d)
}

fn main() {
    let mut raw = String::new();
    io::stdin().read_to_string(&mut raw).expect("read stdin");
    let input: Input = serde_json::from_str(&raw).expect("invalid input JSON");

    let today = parse_day(&input.today);
    let window_start = today - 28;
    let season = (48..=52).contains(&iso_week(today));

    // Daily sales series for the 28 days before today, keyed by sku.
    let mut series: BTreeMap<&str, [f64; 28]> = BTreeMap::new();
    for item in &input.items {
        series.entry(item.sku.as_str()).or_insert([0.0; 28]);
    }
    for sale in &input.sales {
        if let Some(s) = series.get_mut(sale.sku.as_str()) {
            let idx = parse_day(&sale.date) - window_start;
            if (0..28).contains(&idx) {
                s[idx as usize] += sale.qty as f64;
            }
        }
    }

    let mut orders: BTreeMap<String, Order> = BTreeMap::new();
    let mut unknown: Vec<String> = Vec::new();

    for item in &input.items {
        let lead = match resolve_supplier(&item.supplier).and_then(lead_days) {
            Some(d) => d,
            None => {
                unknown.push(item.sku.clone());
                continue;
            }
        };
        let values = &series[item.sku.as_str()];
        let mut forecast = stats::trailing_mean(values, 7);
        if season {
            forecast *= 1.25;
        }
        let safety = stats::percentile(values, 90.0);
        let need = forecast * (lead + 7) as f64 + safety - item.stock as f64;
        if need > 0.0 {
            let whole = need.ceil() as i64;
            let qty = round_up(whole, item.pack);
            // Orders worth less than 500 SEK are not placed (and are not unknown).
            if (qty as f64) * item.price >= 500.0 {
                orders.insert(
                    item.sku.clone(),
                    Order {
                        qty,
                        arrive: format_day(to_weekday(parse_day(&input.today) + lead)),
                    },
                );
            }
        }
    }

    unknown.sort();
    unknown.dedup();
    let out = Output { orders, unknown };
    println!("{}", serde_json::to_string(&out).expect("serialize"));
}
