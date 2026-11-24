// Bridge to libs/stats. Each stdin line is one request:
//   "mean v1 v2 ..."                 -> mean
//   "percentile p v1 v2 ..."         -> percentile(values, p)
//   "trailing_mean w v1 v2 ..."      -> trailing_mean(values, w)
// Each stdout line holds the result.
use std::io::{self, BufRead, BufWriter, Write};

fn main() {
    let stdin = io::stdin();
    let mut out = BufWriter::new(io::stdout().lock());
    for line in stdin.lock().lines() {
        let line = line.expect("read stdin");
        let mut parts = line.split_whitespace();
        let op = match parts.next() {
            Some(op) => op.to_string(),
            None => continue,
        };
        let nums: Vec<f64> = parts
            .map(|t| t.parse::<f64>().expect("number"))
            .collect();
        let value = match op.as_str() {
            "mean" => stats::mean(&nums),
            "percentile" => stats::percentile(&nums[1..], nums[0]),
            "trailing_mean" => stats::trailing_mean(&nums[1..], nums[0] as i64),
            other => panic!("unknown op {other}"),
        };
        writeln!(out, "{}", value).expect("write stdout");
    }
    out.flush().expect("flush");
}
