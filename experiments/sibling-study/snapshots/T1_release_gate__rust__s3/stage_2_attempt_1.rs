use serde::{Deserialize, Serialize};
use std::io::{self, Read};

#[derive(Debug, Deserialize)]
struct Input {
    min_range: String,
    artifacts: Vec<ArtifactInput>,
}

#[derive(Debug, Deserialize)]
struct ArtifactInput {
    raw_path: String,
    channel: String,
    size_kb: i64,
}

#[derive(Debug, Serialize)]
struct Output {
    total: usize,
    eligible: usize,
    oversize: usize,
    total_kb: i64,
    max_kb: i64,
    consecutive_rejects: usize,
    freeze: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SizeTier {
    Tiny,
    Standard,
    Large,
    Oversize,
}

impl SizeTier {
    fn from_kb(size_kb: i64) -> Self {
        if size_kb < 100 {
            Self::Tiny
        } else if size_kb <= 1000 {
            Self::Standard
        } else if size_kb <= 5000 {
            Self::Large
        } else {
            Self::Oversize
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Channel {
    Stable,
    Beta,
    Lts,
}

impl Channel {
    fn parse(s: &str) -> Option<Self> {
        match s {
            "stable" => Some(Self::Stable),
            "beta" => Some(Self::Beta),
            "lts" => Some(Self::Lts),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SemVer {
    major: u64,
    minor: u64,
    patch: u64,
    prerelease: Option<String>,
}

impl SemVer {
    fn parse(s: &str) -> Option<Self> {
        let (core, prerelease) = match s.split_once('-') {
            Some((c, pre)) => {
                if !is_valid_semver_prerelease(pre) {
                    return None;
                }
                (c, Some(pre.to_string()))
            }
            None => (s, None),
        };

        let mut parts = core.split('.');
        let major = parse_semver_num(parts.next()?)?;
        let minor = parse_semver_num(parts.next()?)?;
        let patch = parse_semver_num(parts.next()?)?;
        if parts.next().is_some() {
            return None;
        }

        Some(Self {
            major,
            minor,
            patch,
            prerelease,
        })
    }

    fn core_tuple(&self) -> (u64, u64, u64) {
        (self.major, self.minor, self.patch)
    }

    fn is_prerelease(&self) -> bool {
        self.prerelease.is_some()
    }
}

fn parse_semver_num(s: &str) -> Option<u64> {
    if s.is_empty() || !s.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    if s.len() > 1 && s.starts_with('0') {
        return None;
    }
    s.parse::<u64>().ok()
}

fn is_valid_semver_prerelease(pre: &str) -> bool {
    if pre.is_empty() {
        return false;
    }
    for ident in pre.split('.') {
        if ident.is_empty()
            || !ident
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-')
        {
            return false;
        }
        if ident.bytes().all(|b| b.is_ascii_digit()) && ident.len() > 1 && ident.starts_with('0') {
            return false;
        }
    }
    true
}

#[derive(Debug, Clone)]
struct CaretRange {
    min: SemVer,
}

impl CaretRange {
    fn parse(s: &str) -> Option<Self> {
        let rest = s.trim().strip_prefix('^')?.trim();
        let min = SemVer::parse(rest)?;
        if min.is_prerelease() {
            return None;
        }
        Some(Self { min })
    }

    fn matches(&self, ver: &SemVer) -> bool {
        if ver.is_prerelease() {
            return false;
        }
        if ver.core_tuple() < self.min.core_tuple() {
            return false;
        }
        if self.min.major > 0 {
            ver.major == self.min.major
        } else if self.min.minor > 0 {
            ver.major == 0 && ver.minor == self.min.minor
        } else {
            ver.major == 0 && ver.minor == 0 && ver.patch == self.min.patch
        }
    }
}

fn hex_val(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

fn url_decode(input: &str) -> String {
    let bytes = input.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let (Some(hi), Some(lo)) = (hex_val(bytes[i + 1]), hex_val(bytes[i + 2])) {
                out.push((hi << 4) | lo);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn normalize_posix_path(path: &str) -> String {
    if path.is_empty() {
        return ".".to_string();
    }
    let is_abs = path.starts_with('/');
    let mut stack: Vec<&str> = Vec::new();

    for segment in path.split('/') {
        match segment {
            "" | "." => {}
            ".." => {
                if let Some(&last) = stack.last() {
                    if last != ".." {
                        stack.pop();
                    } else if !is_abs {
                        stack.push("..");
                    }
                } else if !is_abs {
                    stack.push("..");
                }
            }
            seg => stack.push(seg),
        }
    }

    if is_abs {
        format!("/{}", stack.join("/"))
    } else if stack.is_empty() {
        ".".to_string()
    } else {
        stack.join("/")
    }
}

fn is_valid_pkg(pkg: &str) -> bool {
    !pkg.is_empty()
        && pkg
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

fn is_valid_ver_format(ver: &str) -> bool {
    let (core, pre_opt) = match ver.split_once('-') {
        Some((c, pre)) => (c, Some(pre)),
        None => (ver, None),
    };

    if let Some(pre) = pre_opt {
        if pre.is_empty()
            || !pre
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'.')
        {
            return false;
        }
    }

    let mut parts = core.split('.');
    for _ in 0..3 {
        match parts.next() {
            Some(p) if !p.is_empty() && p.bytes().all(|b| b.is_ascii_digit()) => {}
            _ => return false,
        }
    }
    parts.next().is_none()
}

fn is_eligible(artifact: &ArtifactInput, tier: SizeTier, range: Option<&CaretRange>) -> bool {
    if tier == SizeTier::Oversize {
        return false;
    }

    let Some(range) = range else {
        return false;
    };

    if Channel::parse(&artifact.channel).is_none() {
        return false;
    }

    let decoded = url_decode(&artifact.raw_path);
    let norm = normalize_posix_path(&decoded);

    let Some((pkg, ver_str)) = norm.split_once('/') else {
        return false;
    };
    if ver_str.contains('/') {
        return false;
    }
    if !is_valid_pkg(pkg) || !is_valid_ver_format(ver_str) {
        return false;
    }

    let Some(ver) = SemVer::parse(ver_str) else {
        return false;
    };
    range.matches(&ver)
}

fn evaluate(input: &Input) -> Output {
    let range = CaretRange::parse(&input.min_range);
    let total = input.artifacts.len();
    let mut eligible = 0usize;
    let mut oversize = 0usize;
    let mut total_kb = 0i64;
    let mut max_kb = 0i64;
    let mut consecutive_rejects = 0usize;
    let mut prev_rejected = false;

    for (idx, artifact) in input.artifacts.iter().enumerate() {
        let tier = SizeTier::from_kb(artifact.size_kb);
        if tier == SizeTier::Oversize {
            oversize += 1;
        }
        let is_elig = is_eligible(artifact, tier, range.as_ref());
        if is_elig {
            eligible += 1;
            prev_rejected = false;
        } else {
            if prev_rejected {
                consecutive_rejects += 1;
            }
            prev_rejected = true;
        }
        total_kb += artifact.size_kb;
        if idx == 0 || artifact.size_kb > max_kb {
            max_kb = artifact.size_kb;
        }
    }

    let freeze = consecutive_rejects >= 2;

    Output {
        total,
        eligible,
        oversize,
        total_kb,
        max_kb,
        consecutive_rejects,
        freeze,
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut raw = String::new();
    io::stdin().read_to_string(&mut raw)?;
    let input: Input = serde_json::from_str(&raw)?;
    let output = evaluate(&input);
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_url_decode_and_norm() {
        assert_eq!(normalize_posix_path(&url_decode("core/1%2E4%2E0")), "core/1.4.0");
        assert_eq!(normalize_posix_path(&url_decode("ui/v1/../1%2E1%2E0")), "ui/1.1.0");
        assert_eq!(normalize_posix_path("./core//1.4.0/"), "core/1.4.0");
        assert_eq!(normalize_posix_path("../core/1.4.0"), "../core/1.4.0");
        assert_eq!(normalize_posix_path("/core/1.4.0"), "/core/1.4.0");
    }

    #[test]
    fn test_caret_ranges() {
        let r1 = CaretRange::parse("^1.2.0").unwrap();
        assert!(r1.matches(&SemVer::parse("1.2.0").unwrap()));
        assert!(r1.matches(&SemVer::parse("1.9.9").unwrap()));
        assert!(!r1.matches(&SemVer::parse("1.1.9").unwrap()));
        assert!(!r1.matches(&SemVer::parse("2.0.0").unwrap()));
        assert!(!r1.matches(&SemVer::parse("1.3.0-rc.1").unwrap()));

        let r0 = CaretRange::parse("^0.2.3").unwrap();
        assert!(r0.matches(&SemVer::parse("0.2.3").unwrap()));
        assert!(r0.matches(&SemVer::parse("0.2.9").unwrap()));
        assert!(!r0.matches(&SemVer::parse("0.2.2").unwrap()));
        assert!(!r0.matches(&SemVer::parse("0.3.0").unwrap()));

        let r00 = CaretRange::parse("^0.0.3").unwrap();
        assert!(r00.matches(&SemVer::parse("0.0.3").unwrap()));
        assert!(!r00.matches(&SemVer::parse("0.0.4").unwrap()));
        assert!(!r00.matches(&SemVer::parse("0.0.2").unwrap()));
    }
}
