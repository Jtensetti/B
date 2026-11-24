"""Go as a relative: read a package's exported functions with go/types, call them across a typed border.

`use go:"strings" as s` borrows the standard library package. `use go:"./geo" as geo` borrows a local Go
module next to the program (a directory with go.mod). B reads every exported, non-generic function whose
parameter and result types it can represent, and skips the rest; it never invents a signature.

Type mapping: int and sized ints -> Int, float64/float32 -> Float, string -> Text, bool -> Bool,
[]T -> List[T], map[string]T -> Dict[Text, T]. A result (T, error) becomes T, and a non-nil error stops
the program with the Go error message.

Calls cross a JSON-lines process boundary to a host program that B generates for the package, builds
once with the local Go toolchain (no network: GOPROXY=off) and caches by content hash.
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

from .types import BError, Signature, Type, parse_descriptor

_HERE = Path(__file__).with_name("gohost")
_CACHE = Path(os.environ.get("B_CACHE_DIR", Path.home() / ".cache" / "b")) / "go"
_INTS = {"int", "int8", "int16", "int32", "int64", "uint", "uint8", "uint16", "uint32", "uint64"}


@dataclass(frozen=True)
class GoFunction:
    name: str
    params: tuple[str, ...]  # Go type strings
    result: str  # Go type string of the value result
    fails: bool  # the last Go result is an error
    signature: Signature


def _go() -> str:
    exe = shutil.which("go")
    if not exe:
        raise BError("E_IMPORT", "The Go toolchain is required for go: imports (go not found)")
    return exe


def _env() -> dict:
    env = dict(os.environ)
    env.update(GOPROXY="off", GOFLAGS="-mod=mod", GOTOOLCHAIN="local", CGO_ENABLED="0")
    return env


def resolve(path: str) -> str:
    """A local package is a directory relative to the program; anything else is an import path."""
    if path.startswith(("./", "../", "/")):
        base = Path(os.environ.get("B_PROGRAM_DIR") or os.getcwd())
        target = (base / path).resolve()
        if not (target / "go.mod").is_file():
            raise BError("E_IMPORT", f"Go package {path} must be a module directory with go.mod")
        return str(target)
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
        raise BError("E_IMPORT", f"Invalid Go import path {path!r}")
    return path


def _describe_tool() -> Path:
    source = (_HERE / "describe.go").read_bytes()
    folder = _CACHE / ("describe-" + hashlib.sha256(source).hexdigest()[:16])
    exe = folder / "describe"
    if not exe.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "main.go").write_bytes(source)
        (folder / "go.mod").write_text("module bdescribe\n\ngo 1.22\n")
        done = subprocess.run([_go(), "build", "-o", str(exe), "."], cwd=folder, env=_env(),
                              capture_output=True, text=True, timeout=300)
        if done.returncode:
            raise BError("E_IMPORT", "Could not build B's Go describe tool: " + done.stderr[-800:])
    return exe


def _b_type(go: str) -> str | None:
    if go in _INTS:
        return "Int"
    if go in ("float64", "float32"):
        return "Float"
    if go == "string":
        return "Text"
    if go == "bool":
        return "Bool"
    if go.startswith("[]"):
        inner = _b_type(go[2:])
        return f"List[{inner}]" if inner else None
    match = re.fullmatch(r"map\[string\](.+)", go)
    if match:
        inner = _b_type(match.group(1))
        return f"Dict[Text, {inner}]" if inner else None
    return None


_described: dict[str, dict[str, GoFunction]] = {}


def describe(path: str) -> dict[str, GoFunction]:
    target = resolve(path)
    if target in _described:
        return _described[target]
    done = subprocess.run([str(_describe_tool()), target], capture_output=True, text=True,
                          env=_env(), timeout=120)
    if done.returncode:
        raise BError("E_IMPORT", f"Go package {path} could not be read: {done.stderr.strip()[-500:]}")
    functions = {}
    for f in json.loads(done.stdout)["functions"] or []:
        results = list(f["results"])
        fails = bool(results) and results[-1] == "error"
        if fails:
            results.pop()
        if f["variadic"] or len(results) != 1:
            continue
        params = [_b_type(t) for t in f["params"]]
        result = _b_type(results[0])
        if result is None or any(p is None for p in params):
            continue
        signature = Signature(tuple(parse_descriptor(p) for p in params), parse_descriptor(result))
        functions[f["name"]] = GoFunction(f["name"], tuple(f["params"]), results[0], fails, signature)
    _described[target] = functions
    return functions


def _module_name(directory: str) -> str:
    for line in (Path(directory) / "go.mod").read_text().splitlines():
        if line.startswith("module "):
            return line.split()[1]
    raise BError("E_IMPORT", f"{directory}/go.mod has no module line")


def _host_source(import_path: str, functions: dict[str, GoFunction]) -> str:
    cases = []
    for f in functions.values():
        lines = [f'\tcase "{f.name}":', f"\t\tif len(q.Args) != {len(f.params)} {{ return nil, fmt.Errorf(\"{f.name} expects {len(f.params)} arguments\") }}"]
        for i, t in enumerate(f.params):
            lines.append(f"\t\tvar a{i} {t}")
            lines.append(f"\t\tif err := json.Unmarshal(q.Args[{i}], &a{i}); err != nil {{ return nil, err }}")
        args = ", ".join(f"a{i}" for i in range(len(f.params)))
        if f.fails:
            lines.append(f"\t\treturn pkg.{f.name}({args})")
        else:
            lines.append(f"\t\treturn pkg.{f.name}({args}), nil")
        cases.append("\n".join(lines))
    return f'''package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"

	pkg "{import_path}"
)

type request struct {{
	Fn   string            `json:"fn"`
	Args []json.RawMessage `json:"args"`
}}

func call(q request) (value any, err error) {{
	defer func() {{
		if r := recover(); r != nil {{
			err = fmt.Errorf("panic: %v", r)
		}}
	}}()
	switch q.Fn {{
{chr(10).join(cases)}
	}}
	return nil, fmt.Errorf("unknown function %s", q.Fn)
}}

func main() {{
	in := json.NewDecoder(bufio.NewReader(os.Stdin))
	w := bufio.NewWriter(os.Stdout)
	out := json.NewEncoder(w)
	for {{
		var q request
		if err := in.Decode(&q); err != nil {{
			return
		}}
		value, err := call(q)
		if err != nil {{
			out.Encode(map[string]any{{"ok": false, "error": err.Error()}})
		}} else {{
			out.Encode(map[string]any{{"ok": true, "value": value}})
		}}
		w.Flush()
	}}
}}
'''


def _source_digest(directory: str) -> str:
    digest = hashlib.sha256()
    for file in sorted(Path(directory).rglob("*")):
        if file.is_file() and file.suffix in (".go", ".mod", ".sum"):
            digest.update(str(file.relative_to(directory)).encode() + b"\0" + file.read_bytes())
    return digest.hexdigest()


def host(path: str) -> Path:
    """Build (once) and return the host executable for a Go package."""
    target = resolve(path)
    functions = describe(path)
    local = target.startswith("/")
    import_path = _module_name(target) if local else target
    main = _host_source(import_path, functions)
    gomod = "module bhost\n\ngo 1.22\n"
    if local:
        gomod += f"\nrequire {import_path} v0.0.0\n\nreplace {import_path} => {target}\n"
    key = hashlib.sha256((main + gomod + (_source_digest(target) if local else "")).encode()).hexdigest()[:20]
    folder = _CACHE / f"host-{key}"
    exe = folder / "host"
    if not exe.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "main.go").write_text(main)
        (folder / "go.mod").write_text(gomod)
        done = subprocess.run([_go(), "build", "-o", str(exe), "."], cwd=folder, env=_env(),
                              capture_output=True, text=True, timeout=600)
        if done.returncode:
            raise BError("E_IMPORT", f"Could not build the Go host for {path}: {done.stderr[-1200:]}")
    return exe


class _GoProcess:
    def __init__(self, exe: Path):
        self.proc = subprocess.Popen([str(exe)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     text=True, encoding="utf-8", bufsize=1)
        self.lock = threading.Lock()

    def call(self, label: str, name: str, args):
        from .runtime import BBoundaryError
        with self.lock:
            if self.proc.poll() is not None:
                raise BBoundaryError(f"Go host for {label} has exited")
            try:
                self.proc.stdin.write(json.dumps({"fn": name, "args": list(args)}, allow_nan=False) + "\n")
                self.proc.stdin.flush()
                line = self.proc.stdout.readline()
                reply = json.loads(line)
            except (OSError, ValueError, TypeError) as exc:
                raise BBoundaryError(f"Go bridge failed: {exc}") from exc
        if not reply.get("ok"):
            from .runtime import ForeignError
            raise ForeignError(f"Go {label}.{name}: {reply.get('error')}")
        return reply.get("value")


class GoModule:
    def __init__(self, path: str):
        self._path = path
        self._process: _GoProcess | None = None

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def invoke(*args):
            if self._process is None:
                self._process = _GoProcess(host(self._path))
            return self._process.call(self._path, name, args)
        return invoke


def go_module(path: str) -> GoModule:
    return GoModule(path)
