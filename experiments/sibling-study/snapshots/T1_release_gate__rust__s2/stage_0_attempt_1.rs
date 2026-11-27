use serde::{Deserialize, Serialize};
use std::io::{self, Read};

#[derive(Debug, Deserialize)]
struct GateInput {
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
struct GateOutput {
    total: usize,
    eligible: usize,
    total_kb: i64,
    max_kb: i64,
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

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct SemVer {
    major: u64,
    minor: u64,
    patch: u64,
    has_prerelease: bool,
}

impl SemVer {
    fn parse(s: &str) -> Option<Self> {
        let (core, prerelease) = match s.split_once('-') {
            Some((c, p)) => (c, Some(p)),
            None => (s, None),
        };

        let mut core_parts = core.split('.');
        let major = parse_semver_number(core_parts.next()?)?;
        let minor = parse_semver_number(core_parts.next()?)?;
        let patch = parse_semver_number(core_parts.next()?)?;
        if core_parts.next().is_some() {
            return None;
        }

        if let Some(pre) = prerelease {
            if pre.is_empty() {
                return None;
            }
            for ident in pre.split('.') {
                if ident.is_empty()
                    || !ident
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b == b'-')
                {
                    return None;
                }
                if ident.bytes().all(|b| b.is_ascii_digit())
                    && ident.len() > 1
                    && ident.starts_with('0')
                {
                    return None;
                }
            }
        }

        Some(Self {
            major,
            minor,
            patch,
            has_prerelease: prerelease.is_some(),
        })
    }

    fn core_tuple(self) -> (u64, u64, u64) {
        (self.major, self.minor, self.patch)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct CaretRange {
    lower_inclusive: (u64, u64, u64),
    upper_exclusive: (u64, u64, u64),
}

impl CaretRange {
    fn parse(spec: &str) -> Option<Self> {
        let rest = spec.trim().strip_prefix('^')?.trim_start();
        let mut parts = rest.split('.');
        let major = parse_semver_number(parts.next()?)?;
        let minor = parse_semver_number(parts.next()?)?;
        let patch = parse_semver_number(parts.next()?)?;
        if parts.next().is_some() {
            return None;
        }

        let upper_exclusive = if major > 0 {
            (major.checked_add(1)?, 0, 0)
        } else if minor > 0 {
            (0, minor.checked_add(1)?, 0)
        } else {
            (0, 0, patch.checked_add(1)?)
        };

        Some(Self {
            lower_inclusive: (major, minor, patch),
            upper_exclusive,
        })
    }

    fn satisfies(&self, ver: SemVer) -> bool {
        if ver.has_prerelease {
            return false;
        }
        let v = ver.core_tuple();
        v >= self.lower_inclusive && v < self.upper_exclusive
    }
}

fn parse_semver_number(s: &str) -> Option<u64> {
    if s.is_empty() || !s.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    if s.len() > 1 && s.starts_with('0') {
        return None;
    }
    s.parse::<u64>().ok()
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
    let is_abs = path.starts_with('/');
    let mut segments: Vec<&str> = Vec::new();

    for seg in path.split('/') {
        if seg.is_empty() || seg == "." {
            continue;
        }
        if seg == ".." {
            if let Some(&last) = segments.last() {
                if last != ".." {
                    segments.pop();
                    continue;
                }
            }
            if !is_abs {
                segments.push("..");
            }
        } else {
            segments.push(seg);
        }
    }

    if is_abs {
        format!("/{}", segments.join("/"))
    } else if segments.is_empty() {
        ".".to_string()
    } else {
        segments.join("/")
    }
}

fn split_posix_path(norm: &str) -> (&str, &str) {
    match norm.rsplit_once('/') {
        Some(("", base)) => ("/", base),
        Some((dir, base)) => (dir, base),
        None => (".", norm),
    }
}

fn is_valid_pkg(pkg: &str) -> bool {
    !pkg.is_empty()
        && pkg
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

fn is_valid_ver_pattern(ver: &str) -> bool {
    let (core, prerelease) = match ver.split_once('-') {
        Some((c, p)) => (c, Some(p)),
        None => (ver, None),
    };

    let mut parts = core.split('.');
    let valid_core = match (parts.next(), parts.next(), parts.next(), parts.next()) {
        (Some(a), Some(b), Some(c), None) => {
            !a.is_empty()
                && a.bytes().all(|ch| ch.is_ascii_digit())
                && !b.is_empty()
                && b.bytes().all(|ch| ch.is_ascii_digit())
                && !c.is_empty()
                && c.bytes().all(|ch| ch.is_ascii_digit())
        }
        _ => false,
    };
    if !valid_core {
        return false;
    }

    if let Some(pre) = prerelease {
        if pre.is_empty()
            || !pre
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'.')
        {
            return false;
        }
    }

    true
}

fn is_artifact_eligible(artifact: &ArtifactInput, range: Option<CaretRange>) -> bool {
    let decoded = url_decode(&artifact.raw_path);
    let norm = normalize_posix_path(&decoded);
    let (pkg, ver_str) = split_posix_path(&norm);

    if !is_valid_pkg(pkg) || !is_valid_ver_pattern(ver_str) {
        return false;
    }
    if Channel::parse(&artifact.channel).is_none() {
        return false;
    }

    match (SemVer::parse(ver_str), range) {
        (Some(ver), Some(r)) => r.satisfies(ver),
        _ => false,
    }
}

fn process(input: &GateInput) -> GateOutput {
    let range = CaretRange::parse(&input.min_range);
    let total = input.artifacts.len();
    let mut eligible = 0usize;
    let mut total_kb = 0i64;
    let mut max_kb = 0i64;

    for (idx, artifact) in input.artifacts.iter().enumerate() {
        total_kb += artifact.size_kb;
        if idx == 0 || artifact.size_kb > max_kb {
            max_kb = artifact.size_kb;
        }
        if is_artifact_eligible(artifact, range) {
            eligible += 1;
        }
    }

    GateOutput {
        total,
        eligible,
        total_kb,
        max_kb,
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut raw = String::new();
    io::stdin().read_to_string(&mut raw)?;
    let input: GateInput = serde_json::from_str(&raw)?;
    let output = process(&input);
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}
