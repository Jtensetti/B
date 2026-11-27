use serde::{Deserialize, Serialize};
use std::io::{self, Read};

const MS_PER_SECOND: f64 = 1000.0;
const BUCKET_MODULUS: i64 = 4;
const SPIKE_DELTA_MS: i128 = 100;
const MIN_LABEL_CODEPOINTS: usize = 2;
const MAX_LABEL_CODEPOINTS: usize = 12;

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
    critical: usize,
    warn_or_worse: usize,
    consecutive_breaches: usize,
    spike_steps: usize,
    invalid_labels: usize,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Severity {
    Ok,
    Warn,
    Slow,
    Critical,
}

impl Severity {
    fn classify(ms: i64) -> Self {
        if ms < 200 {
            Self::Ok
        } else if ms <= 500 {
            Self::Warn
        } else if ms <= 1000 {
            Self::Slow
        } else {
            Self::Critical
        }
    }

    fn is_critical(self) -> bool {
        matches!(self, Self::Critical)
    }

    fn is_warn_or_worse(self) -> bool {
        match self {
            Self::Ok => false,
            Self::Warn | Self::Slow | Self::Critical => true,
        }
    }
}

fn normalize_service(raw: &str) -> String {
    raw.trim().to_lowercase()
}

fn is_valid_service_label(normalized: &str) -> bool {
    let codepoints = normalized.chars().count();
    (MIN_LABEL_CODEPOINTS..=MAX_LABEL_CODEPOINTS).contains(&codepoints)
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
    let mut valid_total_ms: i128 = 0;
    let mut valid_count: usize = 0;
    let mut invalid_labels: usize = 0;
    let mut max_ms: Option<i64> = None;
    let mut bucket_zero: usize = 0;
    let mut critical: usize = 0;
    let mut warn_or_worse: usize = 0;
    let mut consecutive_breaches: usize = 0;
    let mut spike_steps: usize = 0;
    let mut prev_ms: Option<i64> = None;
    let mut prev_breach = false;

    for sample in &input.samples {
        let service = normalize_service(&sample.service);
        if is_valid_service_label(&service) {
            valid_count += 1;
            valid_total_ms += i128::from(sample.ms);
        } else {
            invalid_labels += 1;
        }

        let is_breach = (sample.ms as f64) > sla_ms;
        if is_breach {
            breaches += 1;
            overage_ms += sample.ms - sla_ms_int;
            if prev_breach {
                consecutive_breaches += 1;
            }
        }

        if let Some(past_ms) = prev_ms {
            if i128::from(sample.ms) > i128::from(past_ms) + SPIKE_DELTA_MS {
                spike_steps += 1;
            }
        }
        prev_ms = Some(sample.ms);
        prev_breach = is_breach;

        max_ms = Some(match max_ms {
            Some(current_max) => current_max.max(sample.ms),
            None => sample.ms,
        });

        if sample.offset.rem_euclid(BUCKET_MODULUS) == 0 {
            bucket_zero += 1;
        }

        let severity = Severity::classify(sample.ms);
        if severity.is_critical() {
            critical += 1;
        }
        if severity.is_warn_or_worse() {
            warn_or_worse += 1;
        }
    }

    let mean_ms = if valid_count == 0 {
        0
    } else {
        div_round_half_to_even(valid_total_ms, valid_count as i128)
    };

    Output {
        count,
        breaches,
        overage_ms,
        max_ms: max_ms.unwrap_or(0),
        mean_ms,
        bucket_zero,
        critical,
        warn_or_worse,
        consecutive_breaches,
        spike_steps,
        invalid_labels,
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
