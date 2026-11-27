use serde::{Deserialize, Serialize};
use std::io::{self, Read};

#[derive(Debug, Deserialize)]
struct QuoteInput {
    eur_to_sek: f64,
    max_sek: i64,
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
struct QuoteOutput {
    legs: usize,
    valid_legs: usize,
    total_m: i64,
    total_eur_cents: i64,
    total_sek: i64,
    heavy_legs: usize,
    customs_legs: usize,
    long_haul_pairs: usize,
    vip_exempt: usize,
    within_cap: bool,
    max_leg_eur_cents: i64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Zone {
    Se,
    Eu,
    NonEu,
}

impl Zone {
    fn parse(raw: &str) -> Option<Self> {
        match raw.trim().to_uppercase().as_str() {
            "SE" => Some(Self::Se),
            "EU" => Some(Self::Eu),
            "NON-EU" => Some(Self::NonEu),
            _ => None,
        }
    }
}

fn normalize_posix_path(path: &str) -> String {
    if path.is_empty() {
        return ".".to_string();
    }
    let is_abs = path.starts_with('/');
    let mut parts: Vec<&str> = Vec::new();
    for part in path.split('/') {
        match part {
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
            _ => parts.push(part),
        }
    }
    if is_abs {
        if parts.is_empty() {
            "/".to_string()
        } else {
            format!("/{}", parts.join("/"))
        }
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
        && bytes[0].is_ascii_lowercase()
        && bytes[1].is_ascii_lowercase()
        && bytes[2].is_ascii_lowercase()
        && bytes[3] == b'-'
        && bytes[4].is_ascii_digit()
        && bytes[5].is_ascii_digit()
}

fn round_half_to_even(value: f64) -> i64 {
    let floor = value.floor();
    let frac = value - floor;
    let rounded = if frac > 0.5 {
        floor + 1.0
    } else if frac < 0.5 {
        floor
    } else if (floor as i64) % 2 == 0 {
        floor
    } else {
        floor + 1.0
    };
    rounded as i64
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

fn evaluate_quote(input: &QuoteInput) -> QuoteOutput {
    let mut valid_legs: usize = 0;
    let mut heavy_legs: usize = 0;
    let mut customs_legs: usize = 0;
    let mut long_haul_pairs: usize = 0;
    let mut vip_exempt: usize = 0;
    let mut prev_long_haul = false;
    let mut total_km: f64 = 0.0;
    let mut total_eur: f64 = 0.0;
    let mut max_leg_eur_cents: Option<i64> = None;

    for leg in &input.legs {
        let norm_route = normalize_posix_path(&leg.route);
        let depot = posix_basename(&norm_route);
        let Some(zone) = Zone::parse(&leg.zone) else {
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
            heavy_legs += 1;
            if depot == "sto-01" && zone == Zone::Se {
                vip_exempt += 1;
            } else {
                leg_eur += 12.0;
            }
        }
        match zone {
            Zone::Se => leg_eur *= 0.9,
            Zone::Eu => {}
            Zone::NonEu => {
                leg_eur += 15.0;
                customs_legs += 1;
            }
        }

        let leg_eur_cents = round_half_to_even(leg_eur * 100.0);
        max_leg_eur_cents = Some(match max_leg_eur_cents {
            Some(current_max) => current_max.max(leg_eur_cents),
            None => leg_eur_cents,
        });

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
    let total_sek = round_half_to_even(total_eur * input.eur_to_sek);

    QuoteOutput {
        legs: input.legs.len(),
        valid_legs,
        total_m: round_half_to_even(total_km * 1000.0),
        total_eur_cents: round_half_to_even(total_eur * 100.0),
        total_sek,
        heavy_legs,
        customs_legs,
        long_haul_pairs,
        vip_exempt,
        within_cap: total_sek <= input.max_sek,
        max_leg_eur_cents: max_leg_eur_cents.unwrap_or(0),
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut buf = String::new();
    io::stdin().read_to_string(&mut buf)?;
    let input: QuoteInput = serde_json::from_str(&buf)?;
    let output = evaluate_quote(&input);
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}
