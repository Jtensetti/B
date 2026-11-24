//! Demand statistics. Maintained by the analytics team.

/// Arithmetic mean; 0.0 for an empty slice.
pub fn mean(values: &[f64]) -> f64 {
    if values.is_empty() { 0.0 } else { values.iter().sum::<f64>() / values.len() as f64 }
}

/// Percentile by nearest rank on the sorted values (p in 0..=100); 0.0 for an empty slice.
pub fn percentile(values: &[f64], p: f64) -> f64 {
    if values.is_empty() { return 0.0; }
    let mut v = values.to_vec();
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let rank = ((p / 100.0) * v.len() as f64).ceil().max(1.0) as usize;
    v[rank.min(v.len()) - 1]
}

/// Mean of the last `window` values (all values when there are fewer); 0.0 for an empty slice.
pub fn trailing_mean(values: &[f64], window: i64) -> f64 {
    let n = values.len();
    let w = (window.max(1) as usize).min(n);
    if n == 0 { 0.0 } else { mean(&values[n - w..]) }
}
