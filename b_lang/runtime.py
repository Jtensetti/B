"""Adapters for Python and .NET. This is a trusted-code runtime, NOT a sandbox."""
from __future__ import annotations
import atexit
import importlib
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any
from functools import lru_cache
from .types import Type, INT, FLOAT, BOOL, TEXT, NONE, ANY, parse_descriptor

_EXACT_SCALARS = {INT: int, BOOL: bool, TEXT: str}
_EXACT_BY_DESCRIPTOR = {typ.name: native for typ, native in _EXACT_SCALARS.items()}

class BAssertionError(AssertionError):
    pass

class BExampleError(AssertionError):
    """A stated example of an imported function no longer holds."""
    pass

def text(value) -> str:
    """B's spelling of a scalar: true/false in lower case, as B source writes them."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


class BContractError(AssertionError):
    """A B function requires/ensures condition failed at execution."""
    pass

class BBoundaryError(RuntimeError):
    pass

@lru_cache(maxsize=256)
def _descriptor(text: str) -> Type:
    return parse_descriptor(text)


def _type_mismatch(value: Any, typ: Type) -> BBoundaryError:
    return BBoundaryError(f"Expected {typ} at boundary, got {type(value).__name__}: {value!r}")


def _guard_type(value: Any, typ: Type) -> Any:
    if typ == ANY:
        return value
    if typ == NONE:
        if value is None:
            return None
        raise BBoundaryError(f"Expected None at boundary, got {type(value).__name__}")
    if typ == FLOAT:
        if type(value) not in (int, float):
            raise _type_mismatch(value, typ)
        try:
            result = float(value)
        except (OverflowError, ValueError) as exc:
            raise BBoundaryError("Int is out of representable Float range") from exc
        if not math.isfinite(result):
            raise BBoundaryError("Non-finite Float is forbidden at B boundary")
        return result
    if typ.name == "Option":
        return None if value is None else _guard_type(value, typ.args[0])
    if typ.name == "List":
        if type(value) is not list:
            raise _type_mismatch(value, typ)
        # Snapshots prevent mutation of the foreign value through B's binding.
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
        return [_guard_type(item, element_type) for item in value]
    if typ.name == "Record":
        if type(value) is not dict:
            raise _type_mismatch(value, typ)
        snapshot = {}
        for field in typ.args:
            if field.name in value:
                snapshot[field.name] = _guard_type(value[field.name], field.args[0])
            elif field.args[0].name != "Option":
                raise BBoundaryError(f"Missing field {field.name} at boundary")
        return snapshot  # fields B does not declare are not carried along
    if typ.name == "Dict":
        if type(value) is not dict:
            raise _type_mismatch(value, typ)
        return {_guard_type(key, typ.args[0]): _guard_type(item, typ.args[1])
                for key, item in value.items()}
    expected = _EXACT_SCALARS.get(typ)
    if expected is None:
        raise BBoundaryError(f"Unsupported B boundary type: {typ}")
    if type(value) is not expected:
        raise _type_mismatch(value, typ)
    return value


def guard(value: Any, btype: str) -> Any:
    """Check and snapshot typed values at B's external or annotated boundaries.

    This validates the SHAPE of data, never a dependency's implementation.
    """
    if type(value) is _EXACT_BY_DESCRIPTOR.get(btype):
        return value
    return _guard_type(value, _descriptor(btype))

def py_module(path: str):
    return importlib.import_module(path)

class _DotNetClient:
    def __init__(self):
        if not shutil.which("dotnet"):
            raise BBoundaryError(".NET 10 SDK is required for net: imports (dotnet not found)")
        project = Path(__file__).resolve().parents[1] / "dotnet" / "B.NetHost" / "B.NetHost.csproj"
        if not project.is_file():
            raise BBoundaryError(f".NET adapter project was not found: {project}")
        build = subprocess.run(["dotnet", "build", str(project), "--configuration", "Release", "--nologo", "--verbosity", "quiet"],
            capture_output=True, text=True, timeout=120, check=False)
        if build.returncode:
            raise BBoundaryError(".NET adapter failed to build: " + (build.stderr or build.stdout)[-1500:])
        dll = project.parent / "bin" / "Release" / "net10.0" / "B.NetHost.dll"
        self.proc = subprocess.Popen(["dotnet", str(dll)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1)
        atexit.register(self.close)

    def call(self, typ: str, method: str, args: tuple[Any, ...]):
        # JSON values only: object identity, callbacks and arbitrary handles are out of scope.
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
            if _client is None: _client = _DotNetClient()
            return _client.call(self.fullname, method, args)
        return invoke

def net_module(fullname: str):
    if fullname not in ("System.Math", "System.Text.RegularExpressions.Regex"):
        raise BBoundaryError(f"Unregistered .NET type: {fullname}")
    return _DotNetType(fullname)
