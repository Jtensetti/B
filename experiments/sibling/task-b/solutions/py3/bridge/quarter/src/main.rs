// Driver: reads one f64 per line on stdin, prints quarter::round_up of each.
use std::io::{self, BufRead, Write};

fn main() {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut out = stdout.lock();
    for line in stdin.lock().lines() {
        let line = line.expect("read");
        let hours: f64 = line.trim().parse().expect("number");
        writeln!(out, "{:?}", quarter::round_up(hours)).expect("write");
    }
}
