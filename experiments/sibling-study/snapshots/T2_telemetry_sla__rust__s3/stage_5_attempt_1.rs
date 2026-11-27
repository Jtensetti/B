use std::io::{self, Read};

use serde::{Deserialize, Serialize};

const MS_PER_SECOND: f64 = 1000.0;
const BUCKET_MODULUS: i64 = 4;
const SPIKE_DELTA_MS: i64 = 100;
const MIN_SERVICE_LABEL_CHARS: usize = 2;
const MAX_SERVICE_LABEL_CHARS: usize = 12;
const EXEMPT_SERVICE: &str = "healthcheck";
const REGRESSION_DELTA_MS: i64 = 300;

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

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
enum AuditStatus {
    Red,
    Yellow,
    Green,
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
    invalid_labels: usize,
    exempt: usize,
    regressed: usize,
    status: AuditStatus,
}

struct EvaluatedSample {
    ms: i64,
    in_bucket_zero: bool,
    label_valid: bool,
    breached: bool,
    exempted_breach: bool,
    severity: Severity,
}

fn is_raw_breach(ms: i64, sla_ms: f64) -> bool {
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

fn is_valid_service_label(normalized_service: &str) -> bool {
    let char_count = normalized_service.chars().count();
    (MIN_SERVICE_LABEL_CHARS..=MAX_SERVICE_LABEL_CHARS).contains(&char_count)
}

fn evaluate_sample(sample: &RawSample, sla_ms: f64) -> EvaluatedSample {
    let normalized_service = normalize_service(&sample.service);
    let in_bucket_zero = sample.offset.rem_euclid(BUCKET_MODULUS) == 0;
    let label_valid = is_valid_service_label(&normalized_service);
    let raw_breach = is_raw_breach(sample.ms, sla_ms);
    let maintenance_exempt = normalized_service == EXEMPT_SERVICE && in_bucket_zero;
    let exempted_breach = raw_breach && maintenance_exempt;
    let breached = raw_breach && !maintenance_exempt;
    let severity = classify_severity(sample.ms);

    EvaluatedSample {
        ms: sample.ms,
        in_bucket_zero,
        label_valid,
        breached,
        exempted_breach,
        severity,
    }
}

fn determine_status(
    consecutive_breaches: usize,
    critical: usize,
    breaches: usize,
    invalid_labels: usize,
) -> AuditStatus {
    if consecutive_breaches >= 2 || critical > 0 {
        AuditStatus::Red
    } else if breaches > 0 || invalid_labels > 0 {
        AuditStatus::Yellow
    } else {
        AuditStatus::Green
    }
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

    let evaluated: Vec<EvaluatedSample> = input
        .samples
        .iter()
        .map(|sample| evaluate_sample(sample, sla_ms))
        .collect();

    let count = evaluated.len();
    let mut breaches: usize = 0;
    let mut overage_ms: i64 = 0;
    let mut valid_total_ms: i128 = 0;
    let mut valid_count: usize = 0;
    let mut invalid_labels: usize = 0;
    let mut bucket_zero: usize = 0;
    let mut critical: usize = 0;
    let mut warn_or_worse: usize = 0;
    let mut exempt: usize = 0;

    for sample in &evaluated {
        if sample.label_valid {
            valid_total_ms += i128::from(sample.ms);
            valid_count += 1;
        } else {
            invalid_labels += 1;
        }

        if sample.breached {
            breaches += 1;
            overage_ms += sample.ms - sla_ms_int;
        }

        if sample.exempted_breach {
            exempt += 1;
        }

        if sample.in_bucket_zero {
            bucket_zero += 1;
        }

        match sample.severity {
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
    for pair in evaluated.windows(2) {
        let past = &pair[0];
        let now = &pair[1];
        if past.breached && now.breached {
            consecutive_breaches += 1;
        }
        if i128::from(now.ms) > i128::from(past.ms) + i128::from(SPIKE_DELTA_MS) {
            spike_steps += 1;
        }
    }

    let mut regressed: usize = 0;
    let mut min_earlier_ms: Option<i64> = None;
    for sample in &evaluated {
        if let Some(min_ms) = min_earlier_ms {
            if i128::from(min_ms) + i128::from(REGRESSION_DELTA_MS) < i128::from(sample.ms) {
                regressed += 1;
            }
            if sample.ms < min_ms {
                min_earlier_ms = Some(sample.ms);
            }
        } else {
            min_earlier_ms = Some(sample.ms);
        }
    }

    let max_ms = evaluated.iter().map(|sample| sample.ms).max().unwrap_or(0);

    let mean_ms = if valid_count == 0 {
        0
    } else {
        round_div_ties_even(valid_total_ms, valid_count as i128)
    };

    let status = determine_status(consecutive_breaches, critical, breaches, invalid_labels);

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
        invalid_labels,
        exempt,
        regressed,
        status,
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
