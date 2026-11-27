"""Checked-in Go stdlib metadata snapshot, verified against b-go-host --describe."""
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
    data = json.loads(resources.files("b_lang").joinpath("go-signatures.json").read_text(encoding="utf-8"))
    if data.get("schema") != 1 or not isinstance(data.get("packages"), dict):
        raise BError("E_METADATA", "Unsupported Go manifest format")
    return data


def go_bindings() -> dict[str, Signature]:
    result: dict[str, Signature] = {}
    for pkg, methods in manifest()["packages"].items():
        for row in methods:
            params = tuple(parse_descriptor(name) for name in row["params"])
            result[f"go:{pkg}.{row['name']}"] = Signature(params, parse_descriptor(row["result"]))
    return result


def go_semantics() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for pkg, methods in manifest()["packages"].items():
        for row in methods:
            if row.get("semantics"):
                result[f"go:{pkg}.{row['name']}"] = dict(row["semantics"])
    return result


def ensure_binary() -> Path:
    host_dir = Path(__file__).resolve().parents[1] / "go" / "b-go-host"
    binary = host_dir / "b-go-host"
    source = host_dir / "main.go"
    if not source.is_file():
        raise BError("E_METADATA", f"Go host source not found: {source}")
    if not binary.is_file() or source.stat().st_mtime > binary.stat().st_mtime:
        if shutil.which("go") is None:
            raise BError("E_METADATA", "go toolchain is required to build b-go-host")
        build = subprocess.run(["go", "build", "-o", str(binary), "."], cwd=str(host_dir),
                               capture_output=True, text=True, check=False, timeout=120)
        if build.returncode:
            raise BError("E_METADATA", f"Go host build failed: {(build.stderr or build.stdout)[-1000:]}")
    return binary


def describe_live() -> dict:
    binary = ensure_binary()
    output = subprocess.run([str(binary), "--describe"], capture_output=True,
                            text=True, check=False, timeout=15)
    if output.returncode:
        raise BError("E_METADATA", f"Go introspection failed: {output.stderr[-1000:]}")
    try:
        return json.loads(output.stdout)
    except json.JSONDecodeError as ex:
        raise BError("E_METADATA", "Invalid Go introspection JSON") from ex
