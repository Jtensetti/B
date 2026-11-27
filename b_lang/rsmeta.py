"""Checked-in Rust stdlib metadata snapshot, verified against b-rust-host --describe."""
from __future__ import annotations

import json
import shutil
import subprocess
from functools import lru_cache
from importlib import resources
from pathlib import Path

from .types import BError, Signature, parse_descriptor


@lru_cache(maxsize=1)
def manifest() -> dict:
    data = json.loads(resources.files("b_lang").joinpath("rs-signatures.json").read_text(encoding="utf-8"))
    if data.get("schema") != 1 or not isinstance(data.get("modules"), dict):
        raise BError("E_METADATA", "Unsupported Rust manifest format")
    return data


def rs_bindings() -> dict[str, Signature]:
    result: dict[str, Signature] = {}
    for mod, methods in manifest()["modules"].items():
        for row in methods:
            params = tuple(parse_descriptor(name) for name in row["params"])
            result[f"rs:{mod}.{row['name']}"] = Signature(params, parse_descriptor(row["result"]))
    return result


def rs_semantics() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for mod, methods in manifest()["modules"].items():
        for row in methods:
            if row.get("semantics"):
                result[f"rs:{mod}.{row['name']}"] = dict(row["semantics"])
    return result


def ensure_binary() -> Path:
    host_dir = Path(__file__).resolve().parents[1] / "rust" / "b-rust-host"
    binary = host_dir / "target" / "release" / "b-rust-host"
    source = host_dir / "src" / "main.rs"
    if not source.is_file():
        raise BError("E_METADATA", f"Rust host source not found: {source}")
    if not binary.is_file() or source.stat().st_mtime > binary.stat().st_mtime:
        if shutil.which("cargo") is None:
            raise BError("E_METADATA", "cargo toolchain is required to build b-rust-host")
        build = subprocess.run(["cargo", "build", "--release", "--quiet"], cwd=str(host_dir),
                               capture_output=True, text=True, check=False, timeout=180)
        if build.returncode:
            raise BError("E_METADATA", f"Rust host build failed: {(build.stderr or build.stdout)[-1000:]}")
    return binary


def describe_live() -> dict:
    binary = ensure_binary()
    output = subprocess.run([str(binary), "--describe"], capture_output=True,
                            text=True, check=False, timeout=15)
    if output.returncode:
        raise BError("E_METADATA", f"Rust introspection failed: {output.stderr[-1000:]}")
    try:
        return json.loads(output.stdout)
    except json.JSONDecodeError as ex:
        raise BError("E_METADATA", "Invalid Rust introspection JSON") from ex
