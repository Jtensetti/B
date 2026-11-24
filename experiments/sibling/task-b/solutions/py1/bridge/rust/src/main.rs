// Bridge: reads a JSON array of hours on stdin, writes a JSON array of rounded hours
// using libs/quarter::round_up. Numbers are parsed and printed by hand (no serde).
use std::io::{self, Read, Write};

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).expect("read stdin");
    let body = input.trim().trim_start_matches('[').trim_end_matches(']');
    let mut out = String::from("[");
    if !body.trim().is_empty() {
        for (i, part) in body.split(',').enumerate() {
            let hours: f64 = part.trim().parse().expect("number");
            if i > 0 {
                out.push(',');
            }
            out.push_str(&format!("{:?}", quarter::round_up(hours)));
        }
    }
    out.push(']');
    io::stdout().write_all(out.as_bytes()).expect("write stdout");
}
