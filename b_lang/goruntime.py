"""Persistent Go host runtime adapter for go: imports."""
from __future__ import annotations

import atexit
import json
import subprocess
from threading import RLock
from typing import Any

from .gometa import ensure_binary, manifest
from .runtime import BBoundaryError
from .types import BError


class _GoClient:
    def __init__(self):
        try:
            binary = ensure_binary()
        except BError as exc:
            raise BBoundaryError(str(exc)) from exc
        self._lock = RLock()
        self.proc = subprocess.Popen(
            [str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
        )
        atexit.register(self.close)

    def call(self, package: str, method: str, args: tuple[Any, ...]):
        with self._lock:
            if self.proc.poll() is not None:
                raise BBoundaryError("Go adapter exited unexpectedly")
            try:
                payload = json.dumps({"package": package, "method": method, "args": args}, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise BBoundaryError(f"Cannot serialize Go arguments: {exc}") from exc
            assert self.proc.stdin and self.proc.stdout
            self.proc.stdin.write(payload + "\n")
            self.proc.stdin.flush()
            response = self.proc.stdout.readline()
            if not response:
                raise BBoundaryError("Go adapter closed the connection")
            try:
                message = json.loads(response)
            except json.JSONDecodeError as exc:
                raise BBoundaryError("Invalid response from Go adapter") from exc
            if not message.get("ok"):
                raise BBoundaryError("Go: " + str(message.get("error", "unknown error")))
            return message.get("value")

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.proc.kill()


_client: _GoClient | None = None


class _GoPackage:
    def __init__(self, package: str):
        self.package = package

    def __getattr__(self, method: str):
        if method.startswith("_"):
            raise AttributeError(method)

        def invoke(*args):
            global _client
            if _client is None or _client.proc.poll() is not None:
                _client = _GoClient()
            return _client.call(self.package, method, args)

        return invoke


def go_module(package: str):
    if package not in manifest()["packages"]:
        raise BBoundaryError(f"Unregistered Go package: {package}")
    return _GoPackage(package)
