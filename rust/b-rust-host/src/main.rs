// B Rust host: zero-dependency Rust stdlib bridge with guarded JSON-lines IPC and --describe metadata.
use std::env;
use std::io::{self, BufRead, Write};
use std::path::Path;

#[derive(Debug, Clone)]
enum JVal {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    Arr(Vec<JVal>),
    Obj(Vec<(String, JVal)>),
}

fn parse_json(s: &str) -> Result<JVal, String> {
    let bytes = s.as_bytes();
    let mut i = 0;
    fn skip_ws(b: &[u8], i: &mut usize) {
        while *i < b.len() && matches!(b[*i], b' ' | b'\t' | b'\r' | b'\n') {
            *i += 1;
        }
    }
    fn parse_str(b: &[u8], i: &mut usize) -> Result<String, String> {
        if *i >= b.len() || b[*i] != b'"' {
            return Err("expected string".into());
        }
        *i += 1;
        let mut out = String::new();
        while *i < b.len() {
            let c = b[*i];
            if c == b'"' {
                *i += 1;
                return Ok(out);
            }
            if c == b'\\' {
                *i += 1;
                if *i >= b.len() {
                    return Err("unterminated escape".into());
                }
                match b[*i] {
                    b'"' => { out.push('"'); *i += 1; }
                    b'\\' => { out.push('\\'); *i += 1; }
                    b'/' => { out.push('/'); *i += 1; }
                    b'b' => { out.push('\u{0008}'); *i += 1; }
                    b'f' => { out.push('\u{000C}'); *i += 1; }
                    b'n' => { out.push('\n'); *i += 1; }
                    b'r' => { out.push('\r'); *i += 1; }
                    b't' => { out.push('\t'); *i += 1; }
                    b'u' => {
                        *i += 1;
                        if *i + 4 > b.len() {
                            return Err("short unicode escape".into());
                        }
                        let hex = std::str::from_utf8(&b[*i..*i + 4]).map_err(|_| "bad utf8")?;
                        let code = u16::from_str_radix(hex, 16).map_err(|_| "bad hex")?;
                        *i += 4;
                        if (0xD800..=0xDBFF).contains(&code) {
                            if *i + 6 <= b.len() && b[*i] == b'\\' && b[*i + 1] == b'u' {
                                let hex2 = std::str::from_utf8(&b[*i + 2..*i + 6]).map_err(|_| "bad utf8")?;
                                let low = u16::from_str_radix(hex2, 16).map_err(|_| "bad hex")?;
                                if (0xDC00..=0xDFFF).contains(&low) {
                                    *i += 6;
                                    let cp = 0x10000 + (((code as u32 - 0xD800) << 10) | (low as u32 - 0xDC00));
                                    out.push(char::from_u32(cp).ok_or("bad surrogate")?);
                                    continue;
                                }
                            }
                            return Err("unpaired surrogate".into());
                        }
                        out.push(char::from_u32(code as u32).ok_or("bad codepoint")?);
                    }
                    _ => return Err("invalid escape".into()),
                }
            } else {
                let rest = std::str::from_utf8(&b[*i..]).map_err(|_| "bad utf8")?;
                let ch = rest.chars().next().ok_or("eof")?;
                out.push(ch);
                *i += ch.len_utf8();
            }
        }
        Err("unterminated string".into())
    }
    fn parse_val(b: &[u8], i: &mut usize) -> Result<JVal, String> {
        skip_ws(b, i);
        if *i >= b.len() {
            return Err("unexpected eof".into());
        }
        match b[*i] {
            b'"' => Ok(JVal::Str(parse_str(b, i)?)),
            b'{' => {
                *i += 1;
                skip_ws(b, i);
                let mut pairs = Vec::new();
                if *i < b.len() && b[*i] == b'}' {
                    *i += 1;
                    return Ok(JVal::Obj(pairs));
                }
                loop {
                    skip_ws(b, i);
                    let k = parse_str(b, i)?;
                    skip_ws(b, i);
                    if *i >= b.len() || b[*i] != b':' {
                        return Err("expected ':'".into());
                    }
                    *i += 1;
                    let v = parse_val(b, i)?;
                    pairs.push((k, v));
                    skip_ws(b, i);
                    if *i < b.len() && b[*i] == b',' {
                        *i += 1;
                    } else if *i < b.len() && b[*i] == b'}' {
                        *i += 1;
                        return Ok(JVal::Obj(pairs));
                    } else {
                        return Err("expected ',' or '}'".into());
                    }
                }
            }
            b'[' => {
                *i += 1;
                skip_ws(b, i);
                let mut items = Vec::new();
                if *i < b.len() && b[*i] == b']' {
                    *i += 1;
                    return Ok(JVal::Arr(items));
                }
                loop {
                    items.push(parse_val(b, i)?);
                    skip_ws(b, i);
                    if *i < b.len() && b[*i] == b',' {
                        *i += 1;
                    } else if *i < b.len() && b[*i] == b']' {
                        *i += 1;
                        return Ok(JVal::Arr(items));
                    } else {
                        return Err("expected ',' or ']'".into());
                    }
                }
            }
            b't' if b[*i..].starts_with(b"true") => { *i += 4; Ok(JVal::Bool(true)) }
            b'f' if b[*i..].starts_with(b"false") => { *i += 5; Ok(JVal::Bool(false)) }
            b'n' if b[*i..].starts_with(b"null") => { *i += 4; Ok(JVal::Null) }
            b'-' | b'0'..=b'9' => {
                let start = *i;
                if b[*i] == b'-' { *i += 1; }
                let mut is_float = false;
                while *i < b.len() && b[*i].is_ascii_digit() { *i += 1; }
                if *i < b.len() && b[*i] == b'.' {
                    is_float = true;
                    *i += 1;
                    while *i < b.len() && b[*i].is_ascii_digit() { *i += 1; }
                }
                if *i < b.len() && matches!(b[*i], b'e' | b'E') {
                    is_float = true;
                    *i += 1;
                    if *i < b.len() && matches!(b[*i], b'+' | b'-') { *i += 1; }
                    while *i < b.len() && b[*i].is_ascii_digit() { *i += 1; }
                }
                let raw = std::str::from_utf8(&b[start..*i]).map_err(|_| "bad num")?;
                if is_float {
                    let f: f64 = raw.parse().map_err(|_| "bad float")?;
                    if !f.is_finite() { return Err("non-finite float".into()); }
                    Ok(JVal::Float(f))
                } else if let Ok(v) = raw.parse::<i64>() {
                    Ok(JVal::Int(v))
                } else {
                    let f: f64 = raw.parse().map_err(|_| "int out of range")?;
                    if !f.is_finite() { return Err("non-finite float".into()); }
                    Ok(JVal::Float(f))
                }
            }
            _ => Err("unexpected token".into()),
        }
    }
    let val = parse_val(bytes, &mut i)?;
    skip_ws(bytes, &mut i);
    if i != bytes.len() {
        return Err("trailing characters".into());
    }
    Ok(val)
}

fn json_escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for ch in s.chars() {
        match ch {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

fn to_json(v: &JVal) -> String {
    match v {
        JVal::Null => "null".into(),
        JVal::Bool(b) => if *b { "true" } else { "false" }.into(),
        JVal::Int(n) => n.to_string(),
        JVal::Float(f) => {
            if f.fract() == 0.0 && f.abs() < 1e15 {
                format!("{:.1}", f)
            } else {
                format!("{}", f)
            }
        }
        JVal::Str(s) => json_escape(s),
        JVal::Arr(xs) => {
            let parts: Vec<String> = xs.iter().map(to_json).collect();
            format!("[{}]", parts.join(","))
        }
        JVal::Obj(ps) => {
            let parts: Vec<String> = ps.iter().map(|(k, v)| format!("{}:{}", json_escape(k), to_json(v))).collect();
            format!("{{{}}}", parts.join(","))
        }
    }
}

fn get_field<'a>(obj: &'a [(String, JVal)], name: &str) -> Option<&'a JVal> {
    obj.iter().find(|(k, _)| k == name).map(|(_, v)| v)
}

fn arg_str(args: &[JVal], idx: usize) -> Result<&str, String> {
    match args.get(idx) {
        Some(JVal::Str(s)) => Ok(s.as_str()),
        _ => Err(format!("argument {} must be Text", idx + 1)),
    }
}

fn arg_i64(args: &[JVal], idx: usize) -> Result<i64, String> {
    match args.get(idx) {
        Some(JVal::Int(n)) => Ok(*n),
        _ => Err(format!("argument {} must be Int (i64)", idx + 1)),
    }
}

fn arg_f64(args: &[JVal], idx: usize) -> Result<f64, String> {
    match args.get(idx) {
        Some(JVal::Float(f)) if f.is_finite() => Ok(*f),
        Some(JVal::Int(n)) => Ok(*n as f64),
        _ => Err(format!("argument {} must be numeric", idx + 1)),
    }
}

fn finite(v: f64) -> Result<JVal, String> {
    if v.is_finite() { Ok(JVal::Float(v)) } else { Err("non-finite output rejected".into()) }
}

fn fnv1a_64_hex(s: &str) -> String {
    let mut h: u64 = 0xcbf29ce484222325;
    for &b in s.as_bytes() {
        h ^= b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    format!("{:016x}", h)
}

fn crc32_ieee(s: &str) -> i64 {
    let mut crc: u32 = 0xFFFF_FFFF;
    for &b in s.as_bytes() {
        crc ^= b as u32;
        for _ in 0..8 {
            let mask = (crc & 1).wrapping_neg();
            crc = (crc >> 1) ^ (0xEDB8_8320 & mask);
        }
    }
    (!crc) as i64
}

fn manifest_json() -> &'static str {
    r#"{"schema":1,"runtime":"b-rust-host/rustc1.100","modules":{"std.str":[{"name":"contains","params":["Text","Text"],"result":"Bool"},{"name":"ends_with","params":["Text","Text"],"result":"Bool"},{"name":"is_ascii","params":["Text"],"result":"Bool"},{"name":"len_bytes","params":["Text"],"result":"Int","semantics":{"string_unit":"utf8_bytes"}},{"name":"len_chars","params":["Text"],"result":"Int","semantics":{"string_unit":"codepoints"}},{"name":"replace","params":["Text","Text","Text"],"result":"Text"},{"name":"split","params":["Text","Text"],"result":"List[Text]"},{"name":"starts_with","params":["Text","Text"],"result":"Bool"},{"name":"to_lowercase","params":["Text"],"result":"Text"},{"name":"to_uppercase","params":["Text"],"result":"Text"},{"name":"trim","params":["Text"],"result":"Text"}],"std.f64":[{"name":"abs","params":["Float"],"result":"Float"},{"name":"ceil","params":["Float"],"result":"Float"},{"name":"clamp","params":["Float","Float","Float"],"result":"Float"},{"name":"floor","params":["Float"],"result":"Float"},{"name":"hypot","params":["Float","Float"],"result":"Float"},{"name":"rem_euclid","params":["Float","Float"],"result":"Float","semantics":{"remainder":"euclid"}},{"name":"round","params":["Float"],"result":"Float","semantics":{"rounding":"half_away_zero"}},{"name":"round_ties_even","params":["Float"],"result":"Float","semantics":{"rounding":"half_even"}},{"name":"sqrt","params":["Float"],"result":"Float"}],"std.i64":[{"name":"clamp","params":["Int","Int","Int"],"result":"Int","semantics":{"int_width":"i64"}},{"name":"div_euclid","params":["Int","Int"],"result":"Int","semantics":{"remainder":"euclid","int_width":"i64"}},{"name":"rem_euclid","params":["Int","Int"],"result":"Int","semantics":{"remainder":"euclid","int_width":"i64"}},{"name":"rem_trunc","params":["Int","Int"],"result":"Int","semantics":{"remainder":"trunc","int_width":"i64"}}],"std.path":[{"name":"extension","params":["Text"],"result":"Option[Text]"},{"name":"file_name","params":["Text"],"result":"Option[Text]"},{"name":"join","params":["Text","Text"],"result":"Text"},{"name":"parent","params":["Text"],"result":"Option[Text]"}],"std.hash":[{"name":"crc32","params":["Text"],"result":"Int"},{"name":"fnv1a_hex","params":["Text"],"result":"Text"}]}}"#
}

fn dispatch(module: &str, method: &str, args: &[JVal]) -> Result<JVal, String> {
    match (module, method) {
        ("std.str", "len_bytes") if args.len() == 1 => Ok(JVal::Int(arg_str(args, 0)?.len() as i64)),
        ("std.str", "len_chars") if args.len() == 1 => Ok(JVal::Int(arg_str(args, 0)?.chars().count() as i64)),
        ("std.str", "is_ascii") if args.len() == 1 => Ok(JVal::Bool(arg_str(args, 0)?.is_ascii())),
        ("std.str", "contains") if args.len() == 2 => Ok(JVal::Bool(arg_str(args, 0)?.contains(arg_str(args, 1)?))),
        ("std.str", "starts_with") if args.len() == 2 => Ok(JVal::Bool(arg_str(args, 0)?.starts_with(arg_str(args, 1)?))),
        ("std.str", "ends_with") if args.len() == 2 => Ok(JVal::Bool(arg_str(args, 0)?.ends_with(arg_str(args, 1)?))),
        ("std.str", "to_lowercase") if args.len() == 1 => Ok(JVal::Str(arg_str(args, 0)?.to_lowercase())),
        ("std.str", "to_uppercase") if args.len() == 1 => Ok(JVal::Str(arg_str(args, 0)?.to_uppercase())),
        ("std.str", "trim") if args.len() == 1 => Ok(JVal::Str(arg_str(args, 0)?.trim().to_string())),
        ("std.str", "replace") if args.len() == 3 => Ok(JVal::Str(arg_str(args, 0)?.replace(arg_str(args, 1)?, arg_str(args, 2)?))),
        ("std.str", "split") if args.len() == 2 => {
            let parts = arg_str(args, 0)?.split(arg_str(args, 1)?).map(|p| JVal::Str(p.to_string())).collect();
            Ok(JVal::Arr(parts))
        }
        ("std.f64", "abs") if args.len() == 1 => finite(arg_f64(args, 0)?.abs()),
        ("std.f64", "ceil") if args.len() == 1 => finite(arg_f64(args, 0)?.ceil()),
        ("std.f64", "floor") if args.len() == 1 => finite(arg_f64(args, 0)?.floor()),
        ("std.f64", "round") if args.len() == 1 => finite(arg_f64(args, 0)?.round()),
        ("std.f64", "round_ties_even") if args.len() == 1 => finite(arg_f64(args, 0)?.round_ties_even()),
        ("std.f64", "sqrt") if args.len() == 1 => finite(arg_f64(args, 0)?.sqrt()),
        ("std.f64", "hypot") if args.len() == 2 => finite(arg_f64(args, 0)?.hypot(arg_f64(args, 1)?)),
        ("std.f64", "rem_euclid") if args.len() == 2 => finite(arg_f64(args, 0)?.rem_euclid(arg_f64(args, 1)?)),
        ("std.f64", "clamp") if args.len() == 3 => {
            let (x, lo, hi) = (arg_f64(args, 0)?, arg_f64(args, 1)?, arg_f64(args, 2)?);
            if lo > hi { return Err("clamp requires min <= max".into()); }
            finite(x.clamp(lo, hi))
        }
        ("std.i64", "clamp") if args.len() == 3 => {
            let (x, lo, hi) = (arg_i64(args, 0)?, arg_i64(args, 1)?, arg_i64(args, 2)?);
            if lo > hi { return Err("clamp requires min <= max".into()); }
            Ok(JVal::Int(x.clamp(lo, hi)))
        }
        ("std.i64", "div_euclid") if args.len() == 2 => {
            let (a, b) = (arg_i64(args, 0)?, arg_i64(args, 1)?);
            if b == 0 { return Err("division by zero".into()); }
            a.checked_div_euclid(b).map(JVal::Int).ok_or_else(|| "i64 overflow".into())
        }
        ("std.i64", "rem_euclid") if args.len() == 2 => {
            let (a, b) = (arg_i64(args, 0)?, arg_i64(args, 1)?);
            if b == 0 { return Err("division by zero".into()); }
            a.checked_rem_euclid(b).map(JVal::Int).ok_or_else(|| "i64 overflow".into())
        }
        ("std.i64", "rem_trunc") if args.len() == 2 => {
            let (a, b) = (arg_i64(args, 0)?, arg_i64(args, 1)?);
            if b == 0 { return Err("division by zero".into()); }
            a.checked_rem(b).map(JVal::Int).ok_or_else(|| "i64 overflow".into())
        }
        ("std.path", "file_name") if args.len() == 1 => {
            match Path::new(arg_str(args, 0)?).file_name().and_then(|s| s.to_str()) {
                Some(s) => Ok(JVal::Str(s.to_string())),
                None => Ok(JVal::Null),
            }
        }
        ("std.path", "extension") if args.len() == 1 => {
            match Path::new(arg_str(args, 0)?).extension().and_then(|s| s.to_str()) {
                Some(s) => Ok(JVal::Str(s.to_string())),
                None => Ok(JVal::Null),
            }
        }
        ("std.path", "parent") if args.len() == 1 => {
            match Path::new(arg_str(args, 0)?).parent().and_then(|s| s.to_str()) {
                Some(s) if !s.is_empty() => Ok(JVal::Str(s.to_string())),
                _ => Ok(JVal::Null),
            }
        }
        ("std.path", "join") if args.len() == 2 => {
            let joined = Path::new(arg_str(args, 0)?).join(arg_str(args, 1)?);
            Ok(JVal::Str(joined.to_string_lossy().to_string()))
        }
        ("std.hash", "fnv1a_hex") if args.len() == 1 => Ok(JVal::Str(fnv1a_64_hex(arg_str(args, 0)?))),
        ("std.hash", "crc32") if args.len() == 1 => Ok(JVal::Int(crc32_ieee(arg_str(args, 0)?))),
        _ => Err(format!("unregistered Rust symbol {}.{} (arity {})", module, method, args.len())),
    }
}

fn main() {
    let cli: Vec<String> = env::args().collect();
    if cli.len() == 2 && cli[1] == "--describe" {
        println!("{}", manifest_json());
        return;
    }
    if cli.len() != 1 {
        eprintln!("Unknown option");
        std::process::exit(2);
    }
    let stdin = io::stdin();
    let mut stdout = io::stdout();
    for line in stdin.lock().lines() {
        let Ok(raw) = line else { break };
        if raw.trim().is_empty() { continue; }
        let reply = match parse_json(&raw) {
            Ok(JVal::Obj(fields)) => {
                let module = match get_field(&fields, "module") { Some(JVal::Str(s)) => s.as_str(), _ => "" };
                let method = match get_field(&fields, "method") { Some(JVal::Str(s)) => s.as_str(), _ => "" };
                let args = match get_field(&fields, "args") { Some(JVal::Arr(xs)) => xs.as_slice(), _ => &[] };
                match dispatch(module, method, args) {
                    Ok(v) => format!("{{\"ok\":true,\"value\":{}}}", to_json(&v)),
                    Err(e) => format!("{{\"ok\":false,\"error\":{}}}", json_escape(&e)),
                }
            }
            _ => "{\"ok\":false,\"error\":\"invalid JSON request\"}".into(),
        };
        if writeln!(stdout, "{}", reply).is_err() { break; }
        let _ = stdout.flush();
    }
}
