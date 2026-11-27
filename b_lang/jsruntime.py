"""One persistent Node worker per execution of a B program using js: imports."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from threading import RLock
import weakref

from .runtime import BBoundaryError, guard
from .types import FLOAT, Type, parse_descriptor

MAX_SAFE_INT = 2**53 - 1


def _checked_args(value):
    if type(value) is int and abs(value) > MAX_SAFE_INT:
        raise BBoundaryError(f"Int exceeds JavaScript's safe integer range: {value}")
    if type(value) is list:
        for item in value:
            _checked_args(item)
    if type(value) is dict:
        for item in value.values():
            _checked_args(item)


def _wire_type(typ: Type):
    if typ.name in ("Int", "Float"):
        return [typ.name]
    return [typ.name, *(_wire_type(t) for t in typ.args)]


def _read_result(value, typ):
    # The worker sends Float in round-trippable decimal text, including -0.
    if typ.name == "Float":
        return float(value)
    if typ.name == "Option":
        return None if value is None else _read_result(value, typ.args[0])
    if typ.name == "List":
        return [_read_result(v, typ.args[0]) for v in value]
    if typ.name == "Dict":
        return {k: _read_result(v, typ.args[1]) for k, v in value.items()}
    return value


def _stop(proc):
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    proc.stdin.close()
    proc.stdout.close()


class NodeSession:
    def __init__(self, source_file, signatures):
        self._modules = weakref.WeakValueDictionary()
        self._signatures = {}
        for target, member, params, result in signatures:
            self._signatures.setdefault(target, {})[member] = (params, parse_descriptor(result, allow_custom=True))

        executable = shutil.which("node")
        if not executable:
            raise BBoundaryError("Node.js is required to execute js: imports")
        anchor = Path(source_file).resolve() if source_file else Path.cwd() / "__b_program__.bee"
        host = Path(__file__).with_name("node_host.cjs")
        self._proc = subprocess.Popen([executable, str(host), str(anchor)], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)
        self._lock = RLock()
        self._cleanup = weakref.finalize(self, _stop, self._proc)

    def _request(self, message):
        with self._lock:
            if not self._cleanup.alive or self._proc.poll() is not None:
                raise BBoundaryError("Node session has ended")
            payload = json.dumps(message, allow_nan=False, ensure_ascii=True)
            try:
                self._proc.stdin.write(payload + "\n")
                self._proc.stdin.flush()
                response = self._proc.stdout.readline()
                if not response:
                    raise ValueError("worker closed the connection")
                reply = json.loads(response)
            except (OSError, ValueError) as exc:
                self.close()
                raise BBoundaryError(f"Node bridge failed: {exc}") from exc
            if not reply["ok"]:
                raise BBoundaryError("Node: " + reply["error"])
            return reply.get("value")

    def module(self, name):
        module = self._modules.get(name)
        if module is None:
            self._request({"op": "load", "target": name})
            module = _NodeModule(self, name, self._signatures.get(name, {}))
            self._modules[name] = module
        return module

    def close(self):
        with self._lock:
            self._cleanup()


class _NodeModule:
    def __init__(self, session, name, signatures):
        self._session = session
        self._name = name
        self._signatures = signatures

    def __getattr__(self, name):
        if name not in self._signatures:
            raise BBoundaryError(f"No declared Node signature for {self._name}.{name}")
        params, result = self._signatures[name]

        def invoke(*args):
            if len(args) != len(params):
                raise BBoundaryError(f"Expected {len(params)} arguments for {self._name}.{name}")
            arguments = [guard(v, t) for v, t in zip(args, params)]
            _checked_args(arguments)
            value = self._session._request({"op": "call", "target": self._name, "member": name,
                                            "args": arguments, "result": _wire_type(result)})
            return guard(_read_result(value, result), str(result))
        return invoke
