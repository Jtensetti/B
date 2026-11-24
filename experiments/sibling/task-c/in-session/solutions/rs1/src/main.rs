use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};
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

/// Lead time in days for a supplier (mirrors libs/leadtime, Go `Days`); None for an unknown supplier.
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

/// Known supplier names (mirrors libs/leadtime `Suppliers`), sorted.
const SUPPLIERS: [&str; 5] = ["Baltic Steel", "Fabrikk AS", "Lumo Lighting", "Nordic Timber", "Textil Partner"];

/// Levenshtein edit distance (mirrors node_modules/fastest-levenshtein `distance`), over chars.
fn levenshtein(a: &str, b: &str) -> usize {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    let mut prev: Vec<usize> = (0..=b.len()).collect();
    for i in 1..=a.len() {
        let mut cur = vec![i; b.len() + 1];
        for j in 1..=b.len() {
            let cost = if a[i - 1] == b[j - 1] { 0 } else { 1 };
            cur[j] = (prev[j] + 1).min(cur[j - 1] + 1).min(prev[j - 1] + cost);
        }
        prev = cur;
    }
    prev[b.len()]
}

/// The known supplier closest to `name` if its distance is at most 2 (ties: alphabetically first).
fn closest_supplier(name: &str) -> Option<&'static str> {
    let mut best: Option<(usize, &'static str)> = None;
    for &known in SUPPLIERS.iter() {
        let d = levenshtein(name, known);
        match best {
            Some((bd, _)) if bd <= d => {}
            _ => best = Some((d, known)),
        }
    }
    best.filter(|(d, _)| *d <= 2).map(|(_, n)| n)
}

/// Days since 1970-01-01 for a proleptic Gregorian date (Hinnant's algorithm).
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

fn parse_day(s: &str) -> i64 {
    let mut it = s.split('-').map(|p| p.parse::<i64>().expect("bad date"));
    let (y, m, d) = (it.next().unwrap(), it.next().unwrap(), it.next().unwrap());
    days_from_civil(y, m, d)
}

fn format_day(z: i64) -> String {
    let (y, m, d) = civil_from_days(z);
    format!("{:04}-{:02}-{:02}", y, m, d)
}

/// Mirrors libs/weeks `iso_week`: ISO week number (1-53) of a day number.
fn iso_week(z: i64) -> i64 {
    // 1970-01-01 was a Thursday; ISO weekday Monday=1..Sunday=7.
    let iso_wd = (z + 3).rem_euclid(7) + 1;
    // The Thursday of this ISO week decides the ISO year.
    let thursday = z - iso_wd + 4;
    let (year, _, _) = civil_from_days(thursday);
    (thursday - days_from_civil(year, 1, 1)) / 7 + 1
}

/// Mirrors libs/weeks `to_weekday`: the day itself on Monday to Friday, else the following Monday.
fn to_weekday(z: i64) -> i64 {
    // Python-style weekday: Monday=0 .. Sunday=6; 1970-01-01 was a Thursday (3).
    let mut d = z;
    while (d + 3).rem_euclid(7) >= 5 {
        d += 1;
    }
    d
}

/// Mirrors libs/Packaging `Packs.RoundUp`.
fn round_up(quantity: i64, pack_size: i64) -> i64 {
    if pack_size <= 0 {
        panic!("pack size must be positive");
    }
    if quantity <= 0 {
        return 0;
    }
    (quantity + pack_size - 1) / pack_size * pack_size
}

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).expect("read stdin");
    let input: Input = serde_json::from_str(&input).expect("bad input JSON");

    let today = parse_day(&input.today);
    let window_start = today - 28;

    // Daily sales per sku over the 28 days before today, oldest first.
    let mut series_by_sku: BTreeMap<&str, [f64; 28]> = BTreeMap::new();
    for sale in &input.sales {
        let offset = parse_day(&sale.date) - window_start;
        if (0..28).contains(&offset) {
            let series = series_by_sku.entry(sale.sku.as_str()).or_insert([0.0; 28]);
            series[offset as usize] += sale.qty as f64;
        }
    }

    let mut orders: BTreeMap<String, (i64, String)> = BTreeMap::new();
    let mut unknown: BTreeSet<String> = BTreeSet::new();

    for item in &input.items {
        let lead = match closest_supplier(&item.supplier).and_then(lead_days) {
            Some(l) => l,
            None => {
                unknown.insert(item.sku.clone());
                continue;
            }
        };
        let zeros = [0.0; 28];
        let series: &[f64] = series_by_sku
            .get(item.sku.as_str())
            .map(|s| s.as_slice())
            .unwrap_or(&zeros);

        let mut forecast = stats::trailing_mean(series, 7);
        if (48..=52).contains(&iso_week(today)) {
            forecast *= 1.25;
        }
        let safety = stats::percentile(series, 90.0);
        let need = forecast * ((lead + 7) as f64) + safety - item.stock as f64;

        if need > 0.0 {
            let needed_units = need.ceil() as i64;
            let qty = round_up(needed_units, item.pack);
            if (qty as f64) * item.price < 500.0 {
                continue;
            }
            let arrive = format_day(to_weekday(parse_day(&input.today) + lead));
            orders.insert(item.sku.clone(), (qty, arrive));
        }
    }

    let orders_json: serde_json::Map<String, serde_json::Value> = orders
        .into_iter()
        .map(|(sku, (qty, arrive))| {
            (sku, serde_json::json!({ "qty": qty, "arrive": arrive }))
        })
        .collect();

    let out = serde_json::json!({
        "orders": orders_json,
        "unknown": unknown.into_iter().collect::<Vec<_>>(),
    });
    println!("{}", out);
}
