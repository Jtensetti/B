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

class BAssertionError(AssertionError):
    pass

class BBoundaryError(RuntimeError):
    pass

def guard(value: Any, btype: str) -> Any:
    """Validate and normalize a value at a declared B boundary.

    Integer inputs to Float are explicitly converted to Python float. A JSON
    number emitted as `6` from the .NET host therefore becomes a B Float 6.0.
    Lists are copied when crossing typed boundaries to normalize elements.
    """
    if btype == "Any":
        return value
    if btype == "Float":
        if type(value) not in (int, float):
            raise BBoundaryError(f"Expected Float at boundary, got {type(value).__name__}: {value!r}")
        try:
            result = float(value)
        except (OverflowError, ValueError) as exc:
            raise BBoundaryError("Int is out of representable Float range") from exc
        if not math.isfinite(result):
            raise BBoundaryError("Non-finite Float is forbidden at B boundary")
        return result
    if btype.startswith("List[") and btype.endswith("]"):
        if not isinstance(value, list):
            raise BBoundaryError(f"Expected {btype} at boundary, got {type(value).__name__}: {value!r}")
        inner = btype[5:-1]
        # A guarded list is a snapshot. This avoids partially converting source
        # data and protects the B binding from changes to the external list.
        return [guard(x, inner) for x in value]
    if btype == "Int":
        valid = type(value) is int
    elif btype == "Bool":
        valid = type(value) is bool
    elif btype == "Text":
        valid = type(value) is str
    else:
        raise BBoundaryError(f"Unsupported B boundary type: {btype}")
    if not valid:
        raise BBoundaryError(f"Expected {btype} at boundary, got {type(value).__name__}: {value!r}")
    return value

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
