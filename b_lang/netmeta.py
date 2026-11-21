"""A checked-in .NET metadata snapshot, verified against the host's reflection.

The snapshot is consumed without starting .NET during B's static check.
The CI run asserts it matches the actual .NET host's accepted overloads.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from functools import lru_cache
from importlib import resources
from pathlib import Path

from .types import BError, KNOWN, Signature, Type


@lru_cache(maxsize=1)
def manifest() -> dict:
    data = json.loads(resources.files('b_lang').joinpath('net-signatures.json').read_text(encoding='utf-8'))
    if data.get('schema') != 1 or not isinstance(data.get('types'), dict):
        raise BError('E_METADATA', 'Unsupported .NET manifest format')
    return data


def net_bindings() -> dict[str, Signature]:
    result = {}
    for typ, methods in manifest()['types'].items():
        for row in methods:
            params = tuple(KNOWN[name] for name in row['params'])
            result[f'net:{typ}.{row["name"]}'] = Signature(params, KNOWN[row['result']])
    return result


def describe_live() -> dict:
    if shutil.which('dotnet') is None:
        raise BError('E_METADATA', 'dotnet is required to inspect live .NET metadata')
    project = Path(__file__).resolve().parents[1] / 'dotnet' / 'B.NetHost' / 'B.NetHost.csproj'
    if not project.is_file():
        raise BError('E_METADATA', f'.NET project was not found: {project}')
    build = subprocess.run(['dotnet', 'build', str(project), '-c', 'Release', '--nologo', '-v', 'quiet'],
                           capture_output=True, text=True, check=False, timeout=120)
    if build.returncode:
        raise BError('E_METADATA', f'.NET build failed: {(build.stderr or build.stdout)[-1000:]}')
    dll = project.parent / 'bin' / 'Release' / 'net10.0' / 'B.NetHost.dll'
    output = subprocess.run(['dotnet', str(dll), '--describe'], capture_output=True,
                            text=True, check=False, timeout=15)
    if output.returncode:
        raise BError('E_METADATA', f'.NET introspection failed: {output.stderr[-1000:]}')
    try:
        return json.loads(output.stdout)
    except json.JSONDecodeError as ex:
        raise BError('E_METADATA', 'Invalid .NET introspection JSON') from ex
