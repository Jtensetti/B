// Bridge: reads one number per line on stdin, prints quarter::round_up of each, one per line.
use std::io::{self, Read};

fn main() {
    let mut s = String::new();
    io::stdin().read_to_string(&mut s).expect("read stdin");
    for line in s.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let h: f64 = line.parse().expect("number");
        println!("{:?}", quarter::round_up(h));
    }
}
