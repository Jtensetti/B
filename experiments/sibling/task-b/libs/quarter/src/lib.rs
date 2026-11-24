//! Rounding of worked time. Maintained by the payroll platform team.

/// Rounds hours up to the next quarter hour. Exact quarters are kept: 7.25 stays 7.25, 7.26 becomes 7.5.
/// A tolerance of one second absorbs floating-point noise from minute arithmetic.
pub fn round_up(hours: f64) -> f64 {
    let quarters = hours * 4.0;
    let tolerance = 4.0 / 3600.0;
    (quarters - tolerance).ceil().max(0.0) / 4.0
}
