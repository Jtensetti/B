// Reads one series per line (whitespace-separated numbers) and prints "mean p90 trailing7" for each.
use std::io::{self, BufRead, Write};

fn main() {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut out = io::BufWriter::new(stdout.lock());
    for line in stdin.lock().lines() {
        let line = line.expect("read stdin");
        let values: Vec<f64> = line
            .split_whitespace()
            .map(|t| t.parse::<f64>().expect("number"))
            .collect();
        let m = stats::mean(&values);
        let p = stats::percentile(&values, 90.0);
        let t = stats::trailing_mean(&values, 7);
        writeln!(out, "{} {} {}", m, p, t).expect("write stdout");
    }
}
