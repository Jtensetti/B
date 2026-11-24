"""C# as a relative: read a local project's public static methods by .NET reflection, call them across JSON lines.

`use cs:"./pricing" as p` builds the C# project in that directory (a folder with one .csproj) and borrows
every public static method of its public static classes, as `p.Rates.Discount(...)`. Overloaded, generic
and out/ref methods are left out, and so is any method whose types B cannot represent.

Type mapping: int, long, short, byte -> Int; double, float, decimal -> Float; string -> Text; bool -> Bool;
T[] and List<T> -> List[T]; Dictionary<string, T> -> Dict[Text, T]; T? (Nullable) -> Option[T].
An exception stops the program with its type and message, or gives none with `foreign ... on error`.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from .types import BError, Signature, parse_descriptor

_HOST_PROJECT = Path(__file__).resolve().parents[1] / "dotnet" / "B.CsHost" / "B.CsHost.csproj"
_CACHE = Path(os.environ.get("B_CACHE_DIR", Path.home() / ".cache" / "b")) / "cs"


@dataclass(frozen=True)
class CsFunction:
    name: str
    signature: Signature


def _dotnet() -> str:
    exe = shutil.which("dotnet")
    if not exe:
        raise BError("E_IMPORT", "The .NET SDK is required for cs: imports (dotnet not found)")
    return exe


def _env() -> dict:
    env = dict(os.environ)
    env.update(DOTNET_CLI_TELEMETRY_OPTOUT="1", DOTNET_NOLOGO="1", DOTNET_SKIP_FIRST_TIME_EXPERIENCE="1")
    return env


def _digest(folder: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(folder.rglob("*")):
        if file.is_file() and not {"bin", "obj"} & set(file.relative_to(folder).parts) and file.suffix in (".cs", ".csproj"):
            digest.update(str(file.relative_to(folder)).encode() + b"\0" + file.read_bytes())
    return digest.hexdigest()[:20]


def _build(project: Path, out: Path) -> None:
    if out.is_dir() and any(out.glob("*.dll")):
        return
    done = subprocess.run([_dotnet(), "build", str(project), "-c", "Release", "-o", str(out), "--nologo", "-v", "q"],
                          capture_output=True, text=True, timeout=600, env=_env())
    if done.returncode:
        shutil.rmtree(out, ignore_errors=True)
        raise BError("E_IMPORT", f"Could not build {project.name}: {(done.stdout + done.stderr)[-1500:]}")


def _host() -> Path:
    out = _CACHE / ("host-" + _digest(_HOST_PROJECT.parent))
    _build(_HOST_PROJECT, out)
    return out / "B.CsHost.dll"


def resolve(path: str) -> Path:
    if not path.startswith(("./", "../", "/")):
        raise BError("E_IMPORT", f"cs:{path}: only local C# projects are supported, written as a path such as ./{path}")
    base = Path(os.environ.get("B_PROGRAM_DIR") or os.getcwd())
    target = (base / path).resolve()
    projects = list(target.glob("*.csproj")) if target.is_dir() else []
    if len(projects) != 1:
        raise BError("E_IMPORT", f"C# project {path} must be a directory with exactly one .csproj")
    return projects[0]


def assembly(path: str) -> Path:
    project = resolve(path)
    out = _CACHE / f"{project.stem}-{_digest(project.parent)}"
    _build(project, out)
    return out / f"{project.stem}.dll"


_described: dict[str, dict[str, CsFunction]] = {}


def describe(path: str) -> dict[str, CsFunction]:
    dll = assembly(path)
    if str(dll) in _described:
        return _described[str(dll)]
    done = subprocess.run([_dotnet(), str(_host()), "--describe", str(dll)], capture_output=True, text=True,
                          timeout=120, env=_env())
    if done.returncode:
        raise BError("E_IMPORT", f"C# project {path} could not be read: {done.stderr.strip()[-500:]}")
    functions = {}
    for f in json.loads(done.stdout)["functions"]:
        name = f"{f['type']}.{f['name']}"
        functions[name] = CsFunction(name, Signature(tuple(parse_descriptor(p) for p in f["params"]),
                                                     parse_descriptor(f["result"])))
    _described[str(dll)] = functions
    return functions


class _CsProcess:
    def __init__(self, dll: Path):
        self.proc = subprocess.Popen([_dotnet(), str(_host()), str(dll)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, encoding="utf-8", bufsize=1, env=_env())
        self.lock = threading.Lock()

    def call(self, label: str, typ: str, method: str, args):
        from .runtime import BBoundaryError, ForeignError
        with self.lock:
            if self.proc.poll() is not None:
                raise BBoundaryError(f"C# host for {label} has exited")
            try:
                self.proc.stdin.write(json.dumps({"type": typ, "method": method, "args": list(args)}, allow_nan=False) + "\n")
                self.proc.stdin.flush()
                reply = json.loads(self.proc.stdout.readline())
            except (OSError, ValueError, TypeError) as exc:
                raise BBoundaryError(f"C# bridge failed: {exc}") from exc
        if not reply.get("ok"):
            raise ForeignError(f"C# {label}.{typ}.{method}: {reply.get('error')}")
        return reply.get("value")


class _CsType:
    def __init__(self, module: "CsModule", name: str):
        self._module, self._name = module, name

    def __getattr__(self, method: str):
        if method.startswith("_"):
            raise AttributeError(method)

        def invoke(*args):
            return self._module._session().call(self._module._path, self._name, method, args)
        return invoke


class CsModule:
    def __init__(self, path: str):
        self._path = path
        self._process: _CsProcess | None = None

    def _session(self) -> _CsProcess:
        if self._process is None:
            self._process = _CsProcess(assembly(self._path))
        return self._process

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        return _CsType(self, name)


def cs_module(path: str) -> CsModule:
    return CsModule(path)
