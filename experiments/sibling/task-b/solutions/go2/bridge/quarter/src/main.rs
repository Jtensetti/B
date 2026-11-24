// Line bridge for libs/quarter: one hours value per stdin line, one rounded value per stdout line.
#[path = "../../../libs/quarter/src/lib.rs"]
mod quarter;

use std::io::{self, BufRead, Write};

fn main() {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut out = io::BufWriter::new(stdout.lock());
    for line in stdin.lock().lines() {
        let line = line.expect("read stdin");
        let hours: f64 = line.trim().parse().expect("hours");
        writeln!(out, "{}", quarter::round_up(hours)).expect("write stdout");
    }
}
