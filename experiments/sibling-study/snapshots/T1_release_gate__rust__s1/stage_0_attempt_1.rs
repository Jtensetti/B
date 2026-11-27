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
    total_kb: i64,
    max_kb: i64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct SemVer {
    major: u64,
    minor: u64,
    patch: u64,
    prerelease: Option<String>,
}

impl SemVer {
    fn parse(input: &str) -> Option<Self> {
        let (without_build, build) = match input.split_once('+') {
            Some((left, right)) => (left, Some(right)),
            None => (input, None),
        };
        if let Some(b) = build {
            if b.split('.').any(|part| {
                part.is_empty()
                    || !part
                        .bytes()
                        .all(|c| c.is_ascii_alphanumeric() || c == b'-')
            }) {
                return None;
            }
        }

        let (core, prerelease) = match without_build.split_once('-') {
            Some((left, right)) => (left, Some(right)),
            None => (without_build, None),
        };

        if let Some(pre) = prerelease {
            for part in pre.split('.') {
                if part.is_empty()
                    || !part
                        .bytes()
                        .all(|c| c.is_ascii_alphanumeric() || c == b'-')
                {
                    return None;
                }
                if part.bytes().all(|c| c.is_ascii_digit())
                    && part.len() > 1
                    && part.starts_with('0')
                {
                    return None;
                }
            }
        }

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
            prerelease: prerelease.map(str::to_owned),
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
    if s.is_empty() || !s.bytes().all(|c| c.is_ascii_digit()) {
        return None;
    }
    if s.len() > 1 && s.starts_with('0') {
        return None;
    }
    s.parse::<u64>().ok()
}

#[derive(Debug, Clone, Copy)]
struct CaretRange {
    min: (u64, u64, u64),
    max_excl: (u64, u64, u64),
}

impl CaretRange {
    fn parse(range: &str) -> Option<Self> {
        let trimmed = range.trim();
        let rest = trimmed.strip_prefix('^')?.trim_start();
        let parts: Vec<&str> = rest.split('.').collect();
        match parts.as_slice() {
            [maj, min, pat] => {
                let major = parse_semver_num(maj)?;
                let minor = parse_semver_num(min)?;
                let patch = parse_semver_num(pat)?;
                let max_excl = if major > 0 {
                    (major + 1, 0, 0)
                } else if minor > 0 {
                    (0, minor + 1, 0)
                } else {
                    (0, 0, patch + 1)
                };
                Some(Self {
                    min: (major, minor, patch),
                    max_excl,
                })
            }
            [maj, min] => {
                let major = parse_semver_num(maj)?;
                let minor = parse_semver_num(min)?;
                let max_excl = if major > 0 {
                    (major + 1, 0, 0)
                } else {
                    (0, minor + 1, 0)
                };
                Some(Self {
                    min: (major, minor, 0),
                    max_excl,
                })
            }
            [maj] => {
                let major = parse_semver_num(maj)?;
                Some(Self {
                    min: (major, 0, 0),
                    max_excl: (major + 1, 0, 0),
                })
            }
            _ => None,
        }
    }

    fn matches(&self, version: &SemVer) -> bool {
        if version.is_prerelease() {
            return false;
        }
        let v = version.core_tuple();
        v >= self.min && v < self.max_excl
    }
}

fn hex_val(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

fn url_decode(input: &str) -> Option<String> {
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
    String::from_utf8(out).ok()
}

fn normalize_posix_path(path: &str) -> String {
    if path.is_empty() {
        return ".".to_string();
    }
    let is_abs = path.starts_with('/');
    let mut parts: Vec<&str> = Vec::new();
    for segment in path.split('/') {
        match segment {
            "" | "." => {}
            ".." => {
                if let Some(&last) = parts.last() {
                    if last != ".." {
                        parts.pop();
                    } else if !is_abs {
                        parts.push("..");
                    }
                } else if !is_abs {
                    parts.push("..");
                }
            }
            _ => parts.push(segment),
        }
    }
    if is_abs {
        format!("/{}", parts.join("/"))
    } else if parts.is_empty() {
        ".".to_string()
    } else {
        parts.join("/")
    }
}

fn is_valid_channel(channel: &str) -> bool {
    matches!(channel, "stable" | "beta" | "lts")
}

fn parse_valid_norm_path(norm: &str) -> Option<(&str, &str)> {
    let (pkg, ver) = norm.split_once('/')?;
    if pkg.is_empty()
        || !pkg
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
    {
        return None;
    }

    let (core, pre) = match ver.split_once('-') {
        Some((c, p)) => (c, Some(p)),
        None => (ver, None),
    };

    if let Some(p) = pre {
        if p.is_empty()
            || !p
                .bytes()
                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'.')
        {
            return None;
        }
    }

    let mut nums = core.split('.');
    let valid_core = matches!(
        (nums.next(), nums.next(), nums.next(), nums.next()),
        (Some(a), Some(b), Some(c), None)
            if !a.is_empty() && a.bytes().all(|x| x.is_ascii_digit())
            && !b.is_empty() && b.bytes().all(|x| x.is_ascii_digit())
            && !c.is_empty() && c.bytes().all(|x| x.is_ascii_digit())
    );
    if !valid_core {
        return None;
    }

    Some((pkg, ver))
}

fn is_artifact_eligible(artifact: &ArtifactInput, range: Option<CaretRange>) -> bool {
    if !is_valid_channel(&artifact.channel) {
        return false;
    }
    let decoded = match url_decode(&artifact.raw_path) {
        Some(s) => s,
        None => return false,
    };
    let norm = normalize_posix_path(&decoded);
    let (_pkg, ver_str) = match parse_valid_norm_path(&norm) {
        Some(parts) => parts,
        None => return false,
    };
    let ver = match SemVer::parse(ver_str) {
        Some(v) => v,
        None => return false,
    };
    match range {
        Some(r) => r.matches(&ver),
        None => false,
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut raw_input = String::new();
    io::stdin().read_to_string(&mut raw_input)?;
    let input: Input = serde_json::from_str(&raw_input)?;

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

    let output = Output {
        total,
        eligible,
        total_kb,
        max_kb,
    };
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}
