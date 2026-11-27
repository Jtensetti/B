use std::io::{self, Read};

use serde::{Deserialize, Serialize};

const MS_PER_SECOND: f64 = 1000.0;
const BUCKET_MODULUS: i64 = 4;
const SPIKE_DELTA_MS: i64 = 100;

#[derive(Debug, Deserialize)]
struct AuditInput {
    sla_s: f64,
    samples: Vec<RawSample>,
}

#[derive(Debug, Deserialize)]
struct RawSample {
    service: String,
    ms: i64,
    offset: i64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Severity {
    Ok,
    Warn,
    Slow,
    Critical,
}

#[derive(Debug, Serialize)]
struct AuditReport {
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
}

fn is_breach(ms: i64, sla_ms: f64) -> bool {
    (ms as f64) > sla_ms
}

fn classify_severity(ms: i64) -> Severity {
    if ms < 200 {
        Severity::Ok
    } else if ms <= 500 {
        Severity::Warn
    } else if ms <= 1000 {
        Severity::Slow
    } else {
        Severity::Critical
    }
}

fn normalize_service(service: &str) -> String {
    service.trim().to_lowercase()
}

fn round_div_ties_even(numerator: i128, denominator: i128) -> i64 {
    debug_assert!(denominator > 0);
    let quotient = numerator.div_euclid(denominator);
    let remainder = numerator.rem_euclid(denominator);
    let twice_remainder = remainder * 2;

    let rounded = if twice_remainder < denominator {
        quotient
    } else if twice_remainder > denominator {
        quotient + 1
    } else if quotient % 2 == 0 {
        quotient
    } else {
        quotient + 1
    };

    rounded as i64
}

fn audit_stream(input: &AuditInput) -> AuditReport {
    let sla_ms = input.sla_s * MS_PER_SECOND;
    let sla_ms_int = sla_ms.round_ties_even() as i64;

    let count = input.samples.len();
    let mut breaches: usize = 0;
    let mut overage_ms: i64 = 0;
    let mut total_ms: i128 = 0;
    let mut bucket_zero: usize = 0;
    let mut critical: usize = 0;
    let mut warn_or_worse: usize = 0;

    for sample in &input.samples {
        let _service = normalize_service(&sample.service);
        total_ms += i128::from(sample.ms);

        if is_breach(sample.ms, sla_ms) {
            breaches += 1;
            overage_ms += sample.ms - sla_ms_int;
        }

        if sample.offset.rem_euclid(BUCKET_MODULUS) == 0 {
            bucket_zero += 1;
        }

        match classify_severity(sample.ms) {
            Severity::Ok => {}
            Severity::Warn | Severity::Slow => {
                warn_or_worse += 1;
            }
            Severity::Critical => {
                critical += 1;
                warn_or_worse += 1;
            }
        }
    }

    let mut consecutive_breaches: usize = 0;
    let mut spike_steps: usize = 0;
    for pair in input.samples.windows(2) {
        let past = &pair[0];
        let now = &pair[1];
        if is_breach(past.ms, sla_ms) && is_breach(now.ms, sla_ms) {
            consecutive_breaches += 1;
        }
        if i128::from(now.ms) > i128::from(past.ms) + i128::from(SPIKE_DELTA_MS) {
            spike_steps += 1;
        }
    }

    let max_ms = input
        .samples
        .iter()
        .map(|sample| sample.ms)
        .max()
        .unwrap_or(0);

    let mean_ms = if count == 0 {
        0
    } else {
        round_div_ties_even(total_ms, count as i128)
    };

    AuditReport {
        count,
        breaches,
        overage_ms,
        max_ms,
        mean_ms,
        bucket_zero,
        critical,
        warn_or_worse,
        consecutive_breaches,
        spike_steps,
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut raw_input = String::new();
    io::stdin().read_to_string(&mut raw_input)?;

    let input: AuditInput = serde_json::from_str(&raw_input)?;
    let report = audit_stream(&input);
    let output = serde_json::to_string(&report)?;
    println!("{output}");

    Ok(())
}
