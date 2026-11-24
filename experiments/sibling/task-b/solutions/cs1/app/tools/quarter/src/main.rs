// Batch helper: reads one hours value per line on stdin, writes round_up(hours) per line.
use std::io::{self, BufRead, BufWriter, Write};

fn main() {
    let stdin = io::stdin();
    let mut out = BufWriter::new(io::stdout().lock());
    for line in stdin.lock().lines() {
        let line = line.expect("read stdin");
        let hours: f64 = line.trim().parse().expect("hours value");
        writeln!(out, "{:?}", quarter::round_up(hours)).expect("write stdout");
    }
}
