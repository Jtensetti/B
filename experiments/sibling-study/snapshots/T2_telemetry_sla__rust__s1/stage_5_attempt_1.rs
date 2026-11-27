use serde::{Deserialize, Serialize};
use std::error::Error;
use std::io::{self, Read};

#[derive(Debug, Deserialize)]
struct Input {
    sla_s: f64,
    samples: Vec<Sample>,
}

#[derive(Debug, Deserialize)]
struct Sample {
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
    exempt: usize,
    regressed: usize,
    status: Status,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
enum Status {
    Green,
    Yellow,
    Red,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Severity {
    Ok,
    Warn,
    Slow,
    Critical,
}

fn classify(ms: i64) -> Severity {
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

fn round_half_to_even(value: f64) -> i64 {
    let floor = value.floor();
    let diff = value - floor;
    let rounded = if diff > 0.5 {
        floor + 1.0
    } else if diff < 0.5 {
        floor
    } else if floor % 2.0 == 0.0 {
        floor
    } else {
        floor + 1.0
    };
    rounded as i64
}

fn normalize_service(service: &str) -> String {
    service.trim().to_lowercase()
}

fn is_valid_label(service: &str) -> bool {
    (2..=12).contains(&service.chars().count())
}

fn is_exempt(service: &str, offset: i64) -> bool {
    service == "healthcheck" && offset.rem_euclid(4) == 0
}

fn determine_status(
    consecutive_breaches: usize,
    critical: usize,
    breaches: usize,
    invalid_labels: usize,
) -> Status {
    if consecutive_breaches >= 2 || critical > 0 {
        Status::Red
    } else if breaches > 0 || invalid_labels > 0 {
        Status::Yellow
    } else {
        Status::Green
    }
}

fn audit(input: &Input) -> Output {
    let sla_ms = input.sla_s * 1000.0;
    let sla_ms_int = round_half_to_even(sla_ms);

    let count = input.samples.len();
    let mut breaches = 0usize;
    let mut overage_ms = 0i64;
    let mut max_ms: Option<i64> = None;
    let mut sum_valid_ms = 0i128;
    let mut valid_count = 0usize;
    let mut invalid_labels = 0usize;
    let mut exempt = 0usize;
    let mut bucket_zero = 0usize;
    let mut critical = 0usize;
    let mut warn_or_worse = 0usize;
    let mut consecutive_breaches = 0usize;
    let mut prev_breach = false;
    let mut min_ms_so_far: Option<i64> = None;
    let mut regressed = 0usize;

    for sample in &input.samples {
        let service = normalize_service(&sample.service);
        if is_valid_label(&service) {
            sum_valid_ms += i128::from(sample.ms);
            valid_count += 1;
        } else {
            invalid_labels += 1;
        }

        let raw_breach = (sample.ms as f64) > sla_ms;
        let effective_breach = if raw_breach {
            if is_exempt(&service, sample.offset) {
                exempt += 1;
                false
            } else {
                breaches += 1;
                overage_ms += sample.ms - sla_ms_int;
                true
            }
        } else {
            false
        };

        if prev_breach && effective_breach {
            consecutive_breaches += 1;
        }
        prev_breach = effective_breach;

        max_ms = Some(match max_ms {
            Some(current) => current.max(sample.ms),
            None => sample.ms,
        });

        if let Some(min_prev) = min_ms_so_far {
            if i128::from(min_prev) + 300 < i128::from(sample.ms) {
                regressed += 1;
            }
            min_ms_so_far = Some(min_prev.min(sample.ms));
        } else {
            min_ms_so_far = Some(sample.ms);
        }

        if sample.offset.rem_euclid(4) == 0 {
            bucket_zero += 1;
        }

        let severity = classify(sample.ms);
        if severity == Severity::Critical {
            critical += 1;
        }
        if severity != Severity::Ok {
            warn_or_worse += 1;
        }
    }

    let mean_ms = if valid_count == 0 {
        0
    } else {
        round_half_to_even((sum_valid_ms as f64) / (valid_count as f64))
    };

    let spike_steps = input
        .samples
        .windows(2)
        .filter(|pair| pair[1].ms > pair[0].ms + 100)
        .count();

    let status = determine_status(consecutive_breaches, critical, breaches, invalid_labels);

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
        exempt,
        regressed,
        status,
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut input_text = String::new();
    io::stdin().read_to_string(&mut input_text)?;

    let input: Input = serde_json::from_str(&input_text)?;
    let output = audit(&input);
    println!("{}", serde_json::to_string(&output)?);

    Ok(())
}
