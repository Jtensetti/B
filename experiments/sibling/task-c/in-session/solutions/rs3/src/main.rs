use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, HashMap};
use std::io::{self, Read};

#[derive(Deserialize)]
struct Input {
    today: String,
    items: Vec<Item>,
    #[serde(default)]
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

/// Port of libs/leadtime (Go): delivery days for a known supplier.
fn leadtime_days(supplier: &str) -> Option<i64> {
    match supplier {
        "Nordic Timber" => Some(12),
        "Baltic Steel" => Some(9),
        "Lumo Lighting" => Some(5),
        "Fabrikk AS" => Some(7),
        "Textil Partner" => Some(14),
        _ => None,
    }
}

/// Port of libs/leadtime Suppliers(), sorted.
const SUPPLIERS: [&str; 5] = ["Baltic Steel", "Fabrikk AS", "Lumo Lighting", "Nordic Timber", "Textil Partner"];

/// Port of node_modules/fastest-levenshtein distance (unit-cost edit distance over chars).
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

/// Known supplier name for a (possibly misspelled) supplier: the closest within distance 2,
/// ties going to the alphabetically first name; None when nothing is that close.
fn resolve_supplier(name: &str) -> Option<&'static str> {
    let mut best: Option<(usize, &'static str)> = None;
    for &known in SUPPLIERS.iter() {
        let d = levenshtein(name, known);
        if d <= 2 && best.map_or(true, |(bd, _)| d < bd) {
            best = Some((d, known));
        }
    }
    best.map(|(_, n)| n)
}

/// Port of libs/Packaging (C#) Packs.RoundUp.
fn round_up(quantity: i64, pack_size: i64) -> i64 {
    assert!(pack_size > 0, "pack size must be positive");
    if quantity <= 0 {
        return 0;
    }
    (quantity + pack_size - 1) / pack_size * pack_size
}

/// Days since 1970-01-01 (proleptic Gregorian).
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

/// Port of libs/weeks iso_week, on day numbers.
fn iso_week(z: i64) -> i64 {
    let weekday = (z + 3).rem_euclid(7) + 1; // Monday=1 .. Sunday=7
    let thursday = z - weekday + 4;
    let (year, _, _) = civil_from_days(thursday);
    (thursday - days_from_civil(year, 1, 1)) / 7 + 1
}

fn parse_date(s: &str) -> i64 {
    let mut it = s.split('-').map(|p| p.parse::<i64>().expect("bad date"));
    let (y, m, d) = (it.next().unwrap(), it.next().unwrap(), it.next().unwrap());
    days_from_civil(y, m, d)
}

/// Port of libs/weeks to_weekday, on day numbers: Saturday/Sunday roll forward to Monday.
fn to_weekday(mut z: i64) -> i64 {
    while (z + 3).rem_euclid(7) >= 5 {
        z += 1;
    }
    z
}

/// Port of libs/weeks add_days, on day numbers.
fn format_date(z: i64) -> String {
    let (y, m, d) = civil_from_days(z);
    format!("{:04}-{:02}-{:02}", y, m, d)
}

fn main() {
    let mut raw = String::new();
    io::stdin().read_to_string(&mut raw).expect("read stdin");
    let input: Input = serde_json::from_str(&raw).expect("invalid input JSON");

    let today = parse_date(&input.today);

    // Quantity sold per (sku, day number).
    let mut sold: HashMap<(&str, i64), i64> = HashMap::new();
    for s in &input.sales {
        *sold.entry((s.sku.as_str(), parse_date(&s.date))).or_insert(0) += s.qty;
    }

    let mut orders = BTreeMap::new();
    let mut unknown = Vec::new();

    for item in &input.items {
        let lead = match resolve_supplier(&item.supplier).and_then(leadtime_days) {
            Some(d) => d,
            None => {
                unknown.push(item.sku.clone());
                continue;
            }
        };

        // 28 days before today, oldest first.
        let series: Vec<f64> = (0..28)
            .map(|i| {
                let day = today - 28 + i;
                *sold.get(&(item.sku.as_str(), day)).unwrap_or(&0) as f64
            })
            .collect();

        let mut forecast = stats::trailing_mean(&series, 7);
        if (48..=52).contains(&iso_week(today)) {
            forecast *= 1.25;
        }
        let safety = stats::percentile(&series, 90.0);
        let need = forecast * (lead + 7) as f64 + safety - item.stock as f64;

        if need > 0.0 {
            let qty = round_up(need.ceil() as i64, item.pack);
            if (qty as f64) * item.price < 500.0 {
                continue;
            }
            orders.insert(
                item.sku.clone(),
                Order {
                    qty,
                    arrive: format_date(to_weekday(today + lead)),
                },
            );
        }
    }

    unknown.sort();
    let out = Output { orders, unknown };
    println!("{}", serde_json::to_string(&out).expect("serialize"));
}
