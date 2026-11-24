use std::io::{self, BufRead};
fn main() {
    for line in io::stdin().lock().lines() {
        let line = line.unwrap();
        let p: Vec<&str> = line.split('\t').collect();
        if p[0] == "geo" {
            let v: Vec<f64> = p[1..5].iter().map(|s| s.parse().unwrap()).collect();
            println!("{:?}", geo::road_km(v[0], v[1], v[2], v[3]));
        }
    }
}
