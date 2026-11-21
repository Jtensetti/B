"""Reproduce native B source-adoption coverage without importing target modules.

Run from the B project with `python -m scripts.benchmark_adoption`.
The denominators cover only public functions declared at the module top-level.
"""
from __future__ import annotations

import json
import platform

from b_lang.adoption import audit_adoptable


def main() -> None:
    results = {}
    for module in ("b_examples.pure_kernels", "statistics", "textwrap"):
        summary = audit_adoptable(module)
        results[module] = {
            "adoptable": summary["adoptable"],
            "public_top_level_functions": summary["public_top_level_functions"],
            "accepted": summary["accepted"],
        }
    print(json.dumps({
        "python": platform.python_version(),
        "measure": "B static source subset, not package API coverage",
        "results": results,
        "totality_proven": False,
        "behavior_proven": False,
        "generated_code_model_compared": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
