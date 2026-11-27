use serde::{Deserialize, Serialize};
use std::io::{self, Read};

#[derive(Debug, Deserialize)]
struct QuoteInput {
    eur_to_sek: f64,
    legs: Vec<LegInput>,
}

#[derive(Debug, Deserialize)]
struct LegInput {
    route: String,
    dx_km: f64,
    dy_km: f64,
    weight_g: f64,
    zone: String,
}

fn is_valid_zone(raw: &str) -> bool {
    matches!(raw.trim().to_uppercase().as_str(), "SE" | "EU" | "NON-EU")
}

#[derive(Debug, Serialize)]
struct QuoteOutput {
    legs: usize,
    valid_legs: usize,
    total_m: i64,
    total_eur_cents: i64,
    total_sek: i64,
    heavy_legs: usize,
}

fn distance_multiplier(km: f64) -> f64 {
    if km <= 50.0 {
        1.0
    } else if km <= 200.0 {
        1.15
    } else {
        1.35
    }
}

fn normalize_posix_path(path: &str) -> String {
    if path.is_empty() {
        return ".".to_string();
    }

    let initial_slashes = path.bytes().take_while(|&b| b == b'/').count();
    let is_abs = initial_slashes > 0;
    let prefix = if initial_slashes == 2 {
        "//"
    } else if is_abs {
        "/"
    } else {
        ""
    };

    let mut comps: Vec<&str> = Vec::new();
    for part in path.split('/') {
        if part.is_empty() || part == "." {
            continue;
        }
        if part == ".." {
            if let Some(&last) = comps.last() {
                if last != ".." {
                    comps.pop();
                    continue;
                }
            }
            if !is_abs {
                comps.push("..");
            }
        } else {
            comps.push(part);
        }
    }

    if comps.is_empty() {
        if is_abs {
            prefix.to_string()
        } else {
            ".".to_string()
        }
    } else {
        format!("{}{}", prefix, comps.join("/"))
    }
}

fn posix_basename(norm_path: &str) -> &str {
    match norm_path.rsplit_once('/') {
        Some((_, base)) => base,
        None => norm_path,
    }
}

fn is_valid_depot(depot: &str) -> bool {
    let bytes = depot.as_bytes();
    bytes.len() == 6
        && bytes[0].is_ascii_lowercase()
        && bytes[1].is_ascii_lowercase()
        && bytes[2].is_ascii_lowercase()
        && bytes[3] == b'-'
        && bytes[4].is_ascii_digit()
        && bytes[5].is_ascii_digit()
}

fn round_half_to_even(x: f64) -> i64 {
    let abs = x.abs();
    let floored = abs.floor();
    let frac = abs - floored;
    let rounded_abs = if frac < 0.5 {
        floored as i64
    } else if frac > 0.5 {
        (floored + 1.0) as i64
    } else {
        let f = floored as i64;
        if f % 2 == 0 {
            f
        } else {
            f + 1
        }
    };
    if x < 0.0 {
        -rounded_abs
    } else {
        rounded_abs
    }
}

fn evaluate_quote(input: &QuoteInput) -> QuoteOutput {
    let mut valid_legs: usize = 0;
    let mut heavy_legs: usize = 0;
    let mut total_km: f64 = 0.0;
    let mut total_eur: f64 = 0.0;

    for leg in &input.legs {
        let norm_route = normalize_posix_path(&leg.route);
        let depot = posix_basename(&norm_route);
        if !is_valid_depot(depot) || !is_valid_zone(&leg.zone) {
            continue;
        }

        valid_legs += 1;
        let km = (leg.dx_km * leg.dx_km + leg.dy_km * leg.dy_km).sqrt();
        let kg = leg.weight_g / 1000.0;
        let base_eur = 5.0 + 0.5 * km + 2.0 * kg;
        let mut leg_eur = base_eur * distance_multiplier(km);
        if kg >= 10.0 {
            heavy_legs += 1;
            leg_eur += 12.0;
        }

        total_km += km;
        total_eur += leg_eur;
    }

    QuoteOutput {
        legs: input.legs.len(),
        valid_legs,
        total_m: round_half_to_even(total_km * 1000.0),
        total_eur_cents: round_half_to_even(total_eur * 100.0),
        total_sek: round_half_to_even(total_eur * input.eur_to_sek),
        heavy_legs,
    }
}

fn main() {
    let mut buf = String::new();
    io::stdin()
        .read_to_string(&mut buf)
        .expect("failed to read stdin");

    let input: QuoteInput = serde_json::from_str(&buf).expect("invalid input JSON");
    let output = evaluate_quote(&input);
    let json = serde_json::to_string(&output).expect("failed to serialize output JSON");
    println!("{json}");
}
