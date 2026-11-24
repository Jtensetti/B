"""Rust as a relative: read a crate's public functions with syn, call them across a typed border.

`use rust:"./pricing" as p` borrows a local crate next to the program (a directory with Cargo.toml and
src/lib.rs). B reads every public, non-generic, top-level function in src/lib.rs whose parameter and
result types it can represent, and skips the rest; it never invents a signature.

Type mapping: integer types -> Int, f64/f32 -> Float, String and &str -> Text, bool -> Bool,
Vec<T> and &[T] -> List[T], HashMap<String, T> -> Dict[Text, T], Option<T> -> Option[T].
A result Result<T, E> becomes T, and an Err stops the program with the error's Debug text,
or gives none with `foreign ... on error`.

Calls cross a JSON-lines process boundary to a host binary that B generates for the crate, builds once
with cargo and caches by content hash. The first build fetches serde_json from crates.io.
Not supported yet: crates from crates.io, methods, structs, traits, modules other than lib.rs.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from .types import BError, Signature, parse_descriptor

_HERE = Path(__file__).with_name("rusthost")
_CACHE = Path(os.environ.get("B_CACHE_DIR", Path.home() / ".cache" / "b")) / "rust"
_INTS = {"i8", "i16", "i32", "i64", "i128", "isize", "u8", "u16", "u32", "u64", "u128", "usize"}


@dataclass(frozen=True)
class RustFunction:
    name: str
    owned: tuple[str, ...]  # owned Rust type to deserialize each argument into
    borrowed: tuple[bool, ...]  # pass the argument by reference
    fails: bool  # the result is a Result<T, E>
    signature: Signature


def _cargo() -> str:
    exe = shutil.which("cargo")
    if not exe:
        raise BError("E_IMPORT", "The Rust toolchain is required for rust: imports (cargo not found)")
    return exe


def _env() -> dict:
    env = dict(os.environ)
    env["CARGO_TARGET_DIR"] = str(_CACHE / "target")
    return env


def resolve(path: str) -> Path:
    if not path.startswith(("./", "../", "/")):
        raise BError("E_IMPORT", f"rust:{path}: only local crates are supported, written as a path such as ./{path}")
    base = Path(os.environ.get("B_PROGRAM_DIR") or os.getcwd())
    target = (base / path).resolve()
    if not (target / "Cargo.toml").is_file() or not (target / "src" / "lib.rs").is_file():
        raise BError("E_IMPORT", f"Rust crate {path} must have Cargo.toml and src/lib.rs")
    return target


def _crate_name(directory: Path) -> str:
    match = re.search(r'^\s*name\s*=\s*"([^"]+)"', (directory / "Cargo.toml").read_text(), re.M)
    if not match:
        raise BError("E_IMPORT", f"{directory}/Cargo.toml has no package name")
    return match.group(1)


def _build(folder: Path, cargo_toml: str, main_rs: str, binary: str) -> Path:
    exe = _CACHE / "bin" / folder.name
    if exe.is_file():
        return exe
    (folder / "src").mkdir(parents=True, exist_ok=True)
    (folder / "Cargo.toml").write_text(cargo_toml)
    (folder / "src" / "main.rs").write_text(main_rs)
    done = subprocess.run([_cargo(), "build", "--release", "-q"], cwd=folder, env=_env(),
                          capture_output=True, text=True, timeout=900)
    if done.returncode:
        raise BError("E_IMPORT", f"Could not build the Rust host: {done.stderr[-1500:]}")
    exe.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(_CACHE / "target" / "release" / binary, exe)
    return exe


def _describe_tool() -> Path:
    source = (_HERE / "describe.rs").read_text()
    key = "describe-" + hashlib.sha256(source.encode()).hexdigest()[:16]
    toml = ('[package]\nname = "b_rust_describe"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n'
            'syn = { version = "2", features = ["full"] }\nquote = "1"\nserde_json = "1"\n')
    return _build(_CACHE / key, toml, source, "b_rust_describe")


def _split_args(text: str) -> list[str]:
    parts, depth, current = [], 0, ""
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    return parts + [current]


def _generic(text: str, name: str) -> list[str] | None:
    for prefix in (name, f"std::collections::{name}", f"std::vec::{name}", f"std::option::{name}"):
        if text.startswith(prefix + "<") and text.endswith(">"):
            return _split_args(text[len(prefix) + 1:-1])
    return None


def _map(rust: str) -> tuple[str, str, bool] | None:
    """(B type, owned Rust type, borrowed) for a parameter or result type, or None."""
    t = rust.replace(" ", "")
    borrowed = t.startswith("&")
    t = t.lstrip("&")
    if t in _INTS:
        return "Int", t, borrowed
    if t in ("f64", "f32"):
        return "Float", t, borrowed
    if t in ("String", "str"):
        return "Text", "String", borrowed
    if t == "bool":
        return "Bool", t, borrowed
    if t.startswith("[") and t.endswith("]"):
        inner = _map(t[1:-1])
        return (f"List[{inner[0]}]", f"Vec<{inner[1]}>", borrowed) if inner and not inner[2] else None
    args = _generic(t, "Vec")
    if args and len(args) == 1:
        inner = _map(args[0])
        return (f"List[{inner[0]}]", f"Vec<{inner[1]}>", borrowed) if inner and not inner[2] else None
    args = _generic(t, "HashMap")
    if args and len(args) == 2 and args[0] == "String":
        inner = _map(args[1])
        return (f"Dict[Text, {inner[0]}]", f"std::collections::HashMap<String,{inner[1]}>", borrowed) \
            if inner and not inner[2] else None
    args = _generic(t, "Option")
    if args and len(args) == 1:
        inner = _map(args[0])
        return (f"Option[{inner[0]}]", f"Option<{inner[1]}>", borrowed) if inner and not inner[2] else None
    return None


_described: dict[str, dict[str, RustFunction]] = {}


def describe(path: str) -> dict[str, RustFunction]:
    target = resolve(path)
    lib = target / "src" / "lib.rs"
    key = f"{target}:{hashlib.sha256(lib.read_bytes()).hexdigest()}"
    if key in _described:
        return _described[key]
    done = subprocess.run([str(_describe_tool()), str(lib)], capture_output=True, text=True, timeout=120)
    if done.returncode:
        raise BError("E_IMPORT", f"Rust crate {path} could not be read: {done.stderr.strip()[-500:]}")
    functions = {}
    for f in json.loads(done.stdout)["functions"]:
        if f["result"] is None:
            continue
        result_type, fails = f["result"].replace(" ", ""), False
        args = _generic(result_type, "Result")
        if args and len(args) == 2:
            result_type, fails = args[0], True
        result = _map(result_type)
        params = [_map(p) for p in f["params"]]
        if result is None or result[2] or any(p is None for p in params):
            continue
        signature = Signature(tuple(parse_descriptor(p[0]) for p in params), parse_descriptor(result[0]))
        functions[f["name"]] = RustFunction(f["name"], tuple(p[1] for p in params), tuple(p[2] for p in params),
                                            fails, signature)
    _described[key] = functions
    return functions


def _host_source(crate: str, functions: dict[str, RustFunction]) -> str:
    arms = []
    for f in functions.values():
        lines = [f'        "{f.name}" => {{',
                 f'            if args.len() != {len(f.owned)} {{ return Err("{f.name} expects {len(f.owned)} arguments".to_string()); }}']
        for i, owned in enumerate(f.owned):
            lines.append(f"            let a{i}: {owned} = serde_json::from_value(args[{i}].clone()).map_err(|e| e.to_string())?;")
        call_args = ", ".join(("&" if b else "") + f"a{i}" for i, b in enumerate(f.borrowed))
        call = f"{crate}::{f.name}({call_args})"
        if f.fails:
            call = f"{call}.map_err(|e| format!(\"{{:?}}\", e))?"
        lines.append(f"            serde_json::to_value({call}).map_err(|e| e.to_string())")
        lines.append("        }")
        arms.append("\n".join(lines))
    return f'''use std::io::{{BufRead, Write}};

fn call(name: &str, args: &[serde_json::Value]) -> Result<serde_json::Value, String> {{
    match name {{
{chr(10).join(arms)}
        _ => Err(format!("unknown function {{}}", name)),
    }}
}}

fn main() {{
    let stdin = std::io::stdin();
    let mut out = std::io::stdout();
    for line in stdin.lock().lines() {{
        let line = match line {{ Ok(l) => l, Err(_) => return }};
        let reply = match serde_json::from_str::<serde_json::Value>(&line) {{
            Ok(q) => {{
                let name = q["fn"].as_str().unwrap_or("").to_string();
                let args = q["args"].as_array().cloned().unwrap_or_default();
                match std::panic::catch_unwind(|| call(&name, &args)) {{
                    Ok(Ok(v)) => serde_json::json!({{"ok": true, "value": v}}),
                    Ok(Err(e)) => serde_json::json!({{"ok": false, "error": e}}),
                    Err(_) => serde_json::json!({{"ok": false, "error": "panic"}}),
                }}
            }}
            Err(e) => serde_json::json!({{"ok": false, "error": e.to_string()}}),
        }};
        writeln!(out, "{{}}", reply).ok();
        out.flush().ok();
    }}
}}
'''


def host(path: str) -> Path:
    target = resolve(path)
    functions = describe(path)
    package = _crate_name(target)
    crate = package.replace("-", "_")
    main = _host_source(crate, functions)
    digest = hashlib.sha256(main.encode())
    for file in sorted(target.rglob("*")):
        if file.is_file() and "target" not in file.parts and file.suffix in (".rs", ".toml"):
            digest.update(str(file.relative_to(target)).encode() + b"\0" + file.read_bytes())
    key = "host-" + digest.hexdigest()[:20]
    binary = key.replace("-", "_")
    toml = (f'[package]\nname = "{binary}"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n'
            f'{package} = {{ path = "{target}" }}\nserde_json = "1"\n')
    return _build(_CACHE / key, toml, main, binary)


class _RustProcess:
    def __init__(self, exe: Path):
        self.proc = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, encoding="utf-8", bufsize=1)
        self.lock = threading.Lock()

    def call(self, label: str, name: str, args):
        from .runtime import BBoundaryError, ForeignError
        with self.lock:
            if self.proc.poll() is not None:
                raise BBoundaryError(f"Rust host for {label} has exited")
            try:
                self.proc.stdin.write(json.dumps({"fn": name, "args": list(args)}, allow_nan=False) + "\n")
                self.proc.stdin.flush()
                reply = json.loads(self.proc.stdout.readline())
            except (OSError, ValueError, TypeError) as exc:
                raise BBoundaryError(f"Rust bridge failed: {exc}") from exc
        if not reply.get("ok"):
            raise ForeignError(f"Rust {label}.{name}: {reply.get('error')}")
        return reply.get("value")


class RustModule:
    def __init__(self, path: str):
        self._path = path
        self._process: _RustProcess | None = None

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def invoke(*args):
            if self._process is None:
                self._process = _RustProcess(host(self._path))
            return self._process.call(self._path, name, args)
        return invoke


def rust_module(path: str) -> RustModule:
    return RustModule(path)
