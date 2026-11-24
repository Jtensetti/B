// Bridge to libs/geo. Each stdin line is "lat1 lon1 lat2 lon2"; each stdout line is the road_km value.
use std::io::{self, BufRead, BufWriter, Write};

fn main() {
    let stdin = io::stdin();
    let mut out = BufWriter::new(io::stdout().lock());
    for line in stdin.lock().lines() {
        let line = line.expect("read stdin");
        let v: Vec<f64> = line
            .split_whitespace()
            .map(|s| s.parse::<f64>().expect("float"))
            .collect();
        if v.len() != 4 {
            panic!("expected 4 numbers per line");
        }
        let km = geo::road_km(v[0], v[1], v[2], v[3]);
        writeln!(out, "{}", km).expect("write stdout");
    }
}
