use serde::{Deserialize, Serialize};
use std::io::{self, Read};

const MS_PER_SECOND: f64 = 1000.0;
const BUCKET_MODULUS: i64 = 4;

#[derive(Debug, Deserialize)]
struct Input {
    sla_s: f64,
    samples: Vec<RawSample>,
}

#[derive(Debug, Deserialize)]
struct RawSample {
    service: String,
    ms: i64,
    offset: i64,
}

#[derive(Debug, Serialize)]
struct Output {
    count: usize,
    breaches: usize,
    overage_ms: i64,
    max_ms: i64,
    mean_ms: i64,
    bucket_zero: usize,
}

fn normalize_service(raw: &str) -> String {
    raw.trim().to_lowercase()
}

fn round_half_to_even_f64(value: f64) -> i64 {
    let floor = value.floor();
    let frac = value - floor;
    let rounded = if frac < 0.5 {
        floor
    } else if frac > 0.5 {
        floor + 1.0
    } else if (floor as i64) % 2 == 0 {
        floor
    } else {
        floor + 1.0
    };
    rounded as i64
}

fn div_round_half_to_even(numerator: i128, denominator: i128) -> i64 {
    debug_assert!(denominator > 0);
    let sign = if numerator < 0 { -1 } else { 1 };
    let abs_num = numerator.abs();
    let mut quotient = abs_num / denominator;
    let remainder = abs_num % denominator;
    let twice_remainder = remainder * 2;
    if twice_remainder > denominator || (twice_remainder == denominator && quotient % 2 != 0) {
        quotient += 1;
    }
    (sign * quotient) as i64
}

fn audit_stream(input: &Input) -> Output {
    let sla_ms = input.sla_s * MS_PER_SECOND;
    let sla_ms_int = round_half_to_even_f64(sla_ms);

    let count = input.samples.len();
    let mut breaches: usize = 0;
    let mut overage_ms: i64 = 0;
    let mut total_ms: i128 = 0;
    let mut max_ms: Option<i64> = None;
    let mut bucket_zero: usize = 0;

    for sample in &input.samples {
        let _service = normalize_service(&sample.service);

        if (sample.ms as f64) > sla_ms {
            breaches += 1;
            overage_ms += sample.ms - sla_ms_int;
        }

        total_ms += i128::from(sample.ms);
        max_ms = Some(match max_ms {
            Some(current_max) => current_max.max(sample.ms),
            None => sample.ms,
        });

        if sample.offset.rem_euclid(BUCKET_MODULUS) == 0 {
            bucket_zero += 1;
        }
    }

    let mean_ms = if count == 0 {
        0
    } else {
        div_round_half_to_even(total_ms, count as i128)
    };

    Output {
        count,
        breaches,
        overage_ms,
        max_ms: max_ms.unwrap_or(0),
        mean_ms,
        bucket_zero,
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut buffer = String::new();
    io::stdin().read_to_string(&mut buffer)?;

    let input: Input = serde_json::from_str(&buffer)?;
    let output = audit_stream(&input);

    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}
