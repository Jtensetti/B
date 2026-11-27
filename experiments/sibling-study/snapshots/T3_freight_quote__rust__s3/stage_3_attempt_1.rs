use serde::{Deserialize, Serialize};
use std::io::{self, Read};

#[derive(Debug, Deserialize)]
struct QuoteRequest {
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

#[derive(Debug, Serialize)]
struct QuoteResponse {
    legs: usize,
    valid_legs: usize,
    total_m: i64,
    total_eur_cents: i64,
    total_sek: i64,
    heavy_legs: usize,
    customs_legs: usize,
    long_haul_pairs: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Zone {
    Se,
    Eu,
    NonEu,
}

fn normalize_posix_path(path: &str) -> String {
    let is_abs = path.starts_with('/');
    let mut parts: Vec<&str> = Vec::new();
    for segment in path.split('/') {
        match segment {
            "" | "." => {}
            ".." => {
                if let Some(&last) = parts.last() {
                    if last != ".." {
                        parts.pop();
                    } else if !is_abs {
                        parts.push("..");
                    }
                } else if !is_abs {
                    parts.push("..");
                }
            }
            other => parts.push(other),
        }
    }
    if is_abs {
        format!("/{}", parts.join("/"))
    } else if parts.is_empty() {
        ".".to_string()
    } else {
        parts.join("/")
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
        && bytes[0..3].iter().all(|b| b.is_ascii_lowercase())
        && bytes[3] == b'-'
        && bytes[4..6].iter().all(|b| b.is_ascii_digit())
}

fn parse_zone(raw: &str) -> Option<Zone> {
    match raw.trim().to_uppercase().as_str() {
        "SE" => Some(Zone::Se),
        "EU" => Some(Zone::Eu),
        "NON-EU" => Some(Zone::NonEu),
        _ => None,
    }
}

fn round_half_to_even(value: f64) -> i64 {
    if value < 0.0 {
        return -round_half_to_even(-value);
    }
    let floor = value.floor();
    let frac = value - floor;
    if frac < 0.5 {
        floor as i64
    } else if frac > 0.5 {
        (floor + 1.0) as i64
    } else {
        let n = floor as i64;
        if n % 2 == 0 {
            n
        } else {
            n + 1
        }
    }
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

fn compute_quote(req: &QuoteRequest) -> QuoteResponse {
    let mut valid_legs: usize = 0;
    let mut heavy_legs: usize = 0;
    let mut customs_legs: usize = 0;
    let mut long_haul_pairs: usize = 0;
    let mut prev_long_haul = false;
    let mut total_km: f64 = 0.0;
    let mut total_eur: f64 = 0.0;

    for leg in &req.legs {
        let norm_route = normalize_posix_path(&leg.route);
        let depot = posix_basename(&norm_route);
        let Some(zone) = parse_zone(&leg.zone) else {
            continue;
        };

        if !is_valid_depot(depot) {
            continue;
        }

        let km = (leg.dx_km * leg.dx_km + leg.dy_km * leg.dy_km).sqrt();
        let kg = leg.weight_g / 1000.0;
        let base_eur = 5.0 + 0.5 * km + 2.0 * kg;
        let mut leg_eur = base_eur * distance_multiplier(km);
        if kg >= 10.0 {
            leg_eur += 12.0;
            heavy_legs += 1;
        }
        match zone {
            Zone::Se => leg_eur *= 0.9,
            Zone::Eu => {}
            Zone::NonEu => {
                leg_eur += 15.0;
                customs_legs += 1;
            }
        }

        let is_long_haul = km > 100.0;
        if prev_long_haul && is_long_haul {
            long_haul_pairs += 1;
        }
        prev_long_haul = is_long_haul;

        valid_legs += 1;
        total_km += km;
        total_eur += leg_eur;
    }

    total_eur += 25.0 * (long_haul_pairs as f64);

    QuoteResponse {
        legs: req.legs.len(),
        valid_legs,
        total_m: round_half_to_even(total_km * 1000.0),
        total_eur_cents: round_half_to_even(total_eur * 100.0),
        total_sek: round_half_to_even(total_eur * req.eur_to_sek),
        heavy_legs,
        customs_legs,
        long_haul_pairs,
    }
}

fn main() {
    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .expect("failed to read stdin");

    let req: QuoteRequest = serde_json::from_str(&input).expect("failed to parse input JSON");
    let resp = compute_quote(&req);
    let output = serde_json::to_string(&resp).expect("failed to serialize output JSON");
    println!("{output}");
}
