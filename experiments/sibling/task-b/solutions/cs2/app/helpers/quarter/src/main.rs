// Reads one hours value per line from stdin and writes quarter::round_up of it per line.
use std::io::{self, BufRead, Write};

fn main() {
    let stdout = io::stdout();
    let mut out = io::BufWriter::new(stdout.lock());
    for line in io::stdin().lock().lines() {
        let line = line.expect("read stdin");
        let hours: f64 = line.trim().parse().expect("hours must be a number");
        writeln!(out, "{}", quarter::round_up(hours)).expect("write stdout");
    }
}
