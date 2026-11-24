use std::io::{self, Read};

// Reads a JSON array of [lat1, lon1, lat2, lon2] and prints a JSON array of road kilometres.
fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).expect("read stdin");
    let rows: Vec<[f64; 4]> = serde_json::from_str(&input).expect("parse json");
    let out: Vec<f64> = rows
        .iter()
        .map(|r| geo::road_km(r[0], r[1], r[2], r[3]))
        .collect();
    println!("{}", serde_json::to_string(&out).expect("encode json"));
}
