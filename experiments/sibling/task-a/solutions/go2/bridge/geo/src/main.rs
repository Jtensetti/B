// Reads "lat1 lon1 lat2 lon2" per line on stdin, writes road_km per line.
use std::io::{self, BufRead, Write};

fn main() {
    let stdout = io::stdout();
    let mut out = stdout.lock();
    for line in io::stdin().lock().lines() {
        let line = line.expect("read line");
        let v: Vec<f64> = line
            .split_whitespace()
            .map(|s| s.parse().expect("parse float"))
            .collect();
        writeln!(out, "{}", geo::road_km(v[0], v[1], v[2], v[3])).expect("write");
    }
}
