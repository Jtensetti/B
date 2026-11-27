"""Adapters for Python, .NET, Go, Rust and B's own semantic runtime primitives.

This is a trusted-code runtime, NOT a sandbox.
"""
from __future__ import annotations
import atexit
import importlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from functools import lru_cache
from .types import (
    Type, INT, FLOAT, BOOL, TEXT, NONE, ANY,
    is_dim_int, is_dim_float, parse_descriptor,
)

_EXACT_SCALARS = {INT: int, BOOL: bool, TEXT: str}
_EXACT_BY_DESCRIPTOR = {typ.name: native for typ, native in _EXACT_SCALARS.items()}


class BAssertionError(AssertionError):
    pass


class BContractError(AssertionError):
    """A B function requires/ensures condition failed at execution."""
    pass


class BBoundaryError(RuntimeError):
    pass


@lru_cache(maxsize=256)
def _descriptor(text: str) -> Type:
    return parse_descriptor(text, allow_custom=True)


def _type_mismatch(value: Any, typ: Type) -> BBoundaryError:
    return BBoundaryError(f"Expected {typ} at boundary, got {type(value).__name__}: {value!r}")


def _guard_type(value: Any, typ: Type, records: dict[str, tuple[tuple[str, str], ...]] | None = None) -> Any:
    if typ == ANY:
        return value
    if typ == NONE:
        if value is None:
            return None
        raise BBoundaryError(f"Expected None at boundary, got {type(value).__name__}")
    if typ == FLOAT or is_dim_float(typ):
        if type(value) not in (int, float):
            raise _type_mismatch(value, typ)
        try:
            result = float(value)
        except (OverflowError, ValueError) as exc:
            raise BBoundaryError("Int is out of representable Float range") from exc
        if not math.isfinite(result):
            raise BBoundaryError("Non-finite Float is forbidden at B boundary")
        return result
    if is_dim_int(typ):
        if type(value) is not int:
            raise _type_mismatch(value, typ)
        return value
    if typ.name == "Option":
        return None if value is None else _guard_type(value, typ.args[0], records)
    if typ.name == "List":
        if type(value) is not list:
            raise _type_mismatch(value, typ)
        if not value:
            return []
        element_type = typ.args[0]
        expected = _EXACT_SCALARS.get(element_type)
        if expected is not None:
            snapshot = value.copy()
            for item in snapshot:
                if type(item) is not expected:
                    raise _type_mismatch(item, element_type)
            return snapshot
        return [_guard_type(item, element_type, records) for item in value]
    if typ.name == "Dict":
        if type(value) is not dict:
            raise _type_mismatch(value, typ)
        return {_guard_type(key, typ.args[0], records): _guard_type(item, typ.args[1], records)
                for key, item in value.items()}
    if typ.name == "Record" and typ.args:
        if type(value) is not dict:
            raise _type_mismatch(value, typ)
        out = {}
        for field in typ.args:
            fname, ftype = field.name, field.args[0]
            if fname not in value:
                if ftype.name == "Option":
                    out[fname] = None
                    continue
                raise BBoundaryError(f"Missing required field {fname!r} for record")
            out[fname] = _guard_type(value[fname], ftype, records)
        return out
    if records and typ.name in records:
        if type(value) is not dict:
            raise _type_mismatch(value, typ)
        out = {}
        for field_name, field_type in records[typ.name]:
            if field_name not in value:
                field_desc = _descriptor(field_type)
                if field_desc.name == "Option":
                    out[field_name] = None
                    continue
                raise BBoundaryError(f"Missing required field {field_name!r} for record {typ.name}")
            out[field_name] = _guard_type(value[field_name], _descriptor(field_type), records)
        return out
    expected = _EXACT_SCALARS.get(typ)
    if expected is None:
        raise BBoundaryError(f"Unsupported B boundary type: {typ}")
    if type(value) is not expected:
        raise _type_mismatch(value, typ)
    return value


def guard(value: Any, btype: str, records: dict[str, tuple[tuple[str, str], ...]] | None = None) -> Any:
    """Check and snapshot typed values at B's external or annotated boundaries."""
    if records is None and type(value) is _EXACT_BY_DESCRIPTOR.get(btype):
        return value
    return _guard_type(value, _descriptor(btype), records)


# --- B's own semantic built-in primitives (backend-independent specification) ---

def b_len(value: Any) -> int:
    return len(value)


def b_abs(value: Any) -> Any:
    return abs(value)


def b_min(a: Any, b: Any) -> Any:
    return a if a <= b else b


def b_max(a: Any, b: Any) -> Any:
    return a if a >= b else b


def b_round_even(value: float) -> int:
    f = float(value)
    if not math.isfinite(f):
        raise BBoundaryError("Non-finite Float cannot be rounded")
    return round(f)


def b_round_away(value: float) -> int:
    f = float(value)
    if not math.isfinite(f):
        raise BBoundaryError("Non-finite Float cannot be rounded")
    return int(math.floor(f + 0.5)) if f >= 0.0 else int(math.ceil(f - 0.5))


def b_div_euclid(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("division by zero")
    q = a // b
    r = a - q * b
    if r < 0:
        q += 1 if b < 0 else -1
    return q


def b_rem_euclid(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("division by zero")
    return a - b_div_euclid(a, b) * b


def b_rem_trunc(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("division by zero")
    q = int(a / b) if abs(a) < 2**53 else (abs(a) // abs(b)) * (-1 if (a < 0) ^ (b < 0) else 1)
    return a - q * b


def b_to_text(value: Any) -> str:
    if type(value) is bool:
        return "true" if value else "false"
    if value is None:
        return "none"
    return str(value)


def b_to_float(value: Any) -> float:
    res = float(value)
    if not math.isfinite(res):
        raise BBoundaryError("Non-finite Float is forbidden")
    return res


def b_to_int(value: Any) -> int:
    if type(value) is bool:
        raise BBoundaryError("Cannot convert Bool to Int")
    if type(value) is float and not math.isfinite(value):
        raise BBoundaryError("Non-finite Float cannot convert to Int")
    return int(value)


def b_scalar(value: Any) -> Any:
    return value


def b_stdin_text() -> str:
    return sys.stdin.read()


def b_json_encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def b_from_json(text: str, btype: str, records: dict[str, tuple[tuple[str, str], ...]] | None = None) -> Any:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BBoundaryError(f"Invalid JSON input: {exc.msg}") from exc
    return guard(parsed, btype, records)


def b_record_with(record: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    out = dict(record)
    out.update(updates)
    return out


def b_str_contains(s: str, sub: str) -> bool: return sub in s
def b_str_starts(s: str, pre: str) -> bool: return s.startswith(pre)
def b_str_ends(s: str, suf: str) -> bool: return s.endswith(suf)
def b_str_lower(s: str) -> str: return s.lower()
def b_str_upper(s: str) -> str: return s.upper()
def b_str_trim(s: str) -> str: return s.strip()
def b_str_split(s: str, sep: str) -> list[str]: return s.split(sep)
def b_str_join(xs: list[str], sep: str) -> str: return sep.join(xs)
def b_str_replace(s: str, old: str, new: str) -> str: return s.replace(old, new)


# --- Foreign runtime adapters ---

def py_module(path: str):
    return importlib.import_module(path)


class _DotNetClient:
    def __init__(self):
        if not shutil.which("dotnet"):
            raise BBoundaryError(".NET 10 SDK is required for net: imports (dotnet not found)")
        project = Path(__file__).resolve().parents[1] / "dotnet" / "B.NetHost" / "B.NetHost.csproj"
        if not project.is_file():
            raise BBoundaryError(f".NET adapter project was not found: {project}")
        dll = project.parent / "bin" / "Release" / "net10.0" / "B.NetHost.dll"
        source = project.parent / "Program.cs"
        if not dll.is_file() or (source.is_file() and source.stat().st_mtime > dll.stat().st_mtime):
            build = subprocess.run(
                ["dotnet", "build", str(project), "--configuration", "Release", "--nologo", "--verbosity", "quiet"],
                capture_output=True, text=True, timeout=120, check=False,
            )
            if build.returncode:
                raise BBoundaryError(".NET adapter failed to build: " + (build.stderr or build.stdout)[-1500:])
        self.proc = subprocess.Popen(["dotnet", str(dll)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        atexit.register(self.close)

    def call(self, typ: str, method: str, args: tuple[Any, ...]):
        if self.proc.poll() is not None: raise BBoundaryError(".NET adapter exited unexpectedly")
        try: payload = json.dumps({"type": typ, "method": method, "args": args}, allow_nan=False)
        except (TypeError, ValueError) as e: raise BBoundaryError(f"Cannot serialize .NET arguments: {e}") from e
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(payload + "\n"); self.proc.stdin.flush()
        response = self.proc.stdout.readline()
        if not response: raise BBoundaryError(".NET adapter closed the connection")
        try: message = json.loads(response)
        except json.JSONDecodeError as e: raise BBoundaryError("Invalid response from .NET adapter") from e
        if not message.get("ok"): raise BBoundaryError(".NET: " + str(message.get("error", "unknown error")))
        return message.get("value")

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try: self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired: self.proc.kill()


_client: _DotNetClient | None = None


class _DotNetType:
    def __init__(self, fullname: str): self.fullname = fullname
    def __getattr__(self, method: str):
        if method.startswith("_"): raise AttributeError(method)
        def invoke(*args):
            global _client
            if _client is None or _client.proc.poll() is not None:
                _client = _DotNetClient()
            return _client.call(self.fullname, method, args)
        return invoke


def net_module(fullname: str):
    if fullname not in ("System.Math", "System.Text.RegularExpressions.Regex", "System.Uri"):
        raise BBoundaryError(f"Unregistered .NET type: {fullname}")
    return _DotNetType(fullname)


def go_module(package: str):
    from .goruntime import go_module as _go_module
    return _go_module(package)


def rs_module(module: str):
    from .rsruntime import rs_module as _rs_module
    return _rs_module(module)
