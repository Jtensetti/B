// Driver: reads a JSON array of numbers on stdin and prints, for each, {"ok","value","error"}
// with quarter::round_up applied to it.
use std::io::Read;

fn main() {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input).expect("read stdin");
    let body = input.trim().trim_start_matches('[').trim_end_matches(']');
    let mut out = String::from("[");
    for (i, part) in body.split(',').filter(|s| !s.trim().is_empty()).enumerate() {
        let hours: f64 = part.trim().parse().expect("number");
        if i > 0 {
            out.push(',');
        }
        out.push_str(&format!(
            "{{\"ok\":true,\"value\":{:?},\"error\":null}}",
            quarter::round_up(hours)
        ));
    }
    out.push(']');
    println!("{}", out);
}
