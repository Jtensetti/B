"""Reproducible probe of the B signature reader across large installed libraries.

Usage (from project root): python -m scripts.audit_libraries > results.json
Uninstalled packages are recorded, not installed or imported by this script.
This is NOT a whole-library coverage or correctness benchmark.
"""
from __future__ import annotations
import json
import platform
from b_lang.audit import audit_python
from b_lang.types import BError

MODULES = (
    "b_examples.demo_lib",
    "numpy", "numpy._core.fromnumeric", "numpy.ma.core",
    "pandas", "pandas.core.dtypes.common",
    "scipy", "scipy.stats",
    "sympy.utilities.iterables",
    "pydantic._internal._utils",
)


def main():
    rows = []
    for name in MODULES:
        try:
            row = audit_python(name).to_dict()
        except BError as ex:
            row = {"target": "py:"+name, "error": ex.code, "message": ex.message}
        rows.append(row)
    print(json.dumps({
        "b_version": "0.5", "python_version": platform.python_version(),
        "metric": "direct-declarations-only, NOT public API coverage",
        "modules": rows,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
