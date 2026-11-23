"""Seven unit mistakes in a two-library program, in B and in typed Python.

Each mistake is one edit an author could plausibly make. The script applies it
to both versions and records whether the program is rejected before running,
runs with a correct result, or runs with a wrong result. Run from the
repository root: python experiments/border-units/check.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
B_SOURCE = (HERE / "plan.bee").read_text()
PY_SOURCE = (HERE / "plan.py").read_text()

MISTAKES = [
    ("speed and weight swapped",
     ("takeoff_distance(220 km per h, 1100 kg)", "takeoff_distance(1100 kg, 220 km per h)"),
     ("takeoff_distance(220.0 / KMH_PER_KNOT, 1100.0 * LB_PER_KG)", "takeoff_distance(1100.0 * LB_PER_KG, 220.0 / KMH_PER_KNOT)")),
    ("km/h passed where the library expects knots",
     ("220 km per h", "220"), ("220.0 / KMH_PER_KNOT", "220.0")),
    ("kg passed where the library expects pounds",
     ("1100 kg", "1100"), ("1100.0 * LB_PER_KG", "1100.0")),
    ("meters passed where the library expects feet",
     ("density_altitude(350 m", "density_altitude(350"), ("density_altitude(350.0 / M_PER_FT", "density_altitude(350.0")),
    ("feet result used as meters",
     ("print (runway - roll) as m", "print runway - roll"), ("* LB_PER_KG) * M_PER_FT", "* LB_PER_KG)")),
    ("gallons added to liters",
     ("+ 12 l", "+ 12"), ("* L_PER_GAL + 12.0", "+ 12.0")),
    ("minutes passed where the library expects hours",
     ("fuel_burn(95 min)", "fuel_burn(95 h)"), ("fuel_burn(95.0 / 60.0)", "fuel_burn(95.0)")),
]


def outcome(command, source, suffix, baseline):
    path = HERE / f"_mutant{suffix}"
    path.write_text(source)
    try:
        run = subprocess.run([*command, str(path)], capture_output=True, text=True, cwd=HERE.parents[1])
    finally:
        path.unlink()
    if run.returncode != 0:
        return "rejected before running" if "E_" in run.stderr else "crashed"
    return "correct result" if run.stdout == baseline else "wrong result, no error"


def main():
    b = [sys.executable, "-m", "b_lang.cli", "run"]
    py = [sys.executable]
    b_base = subprocess.run([*b, str(HERE / "plan.bee")], capture_output=True, text=True).stdout
    py_base = subprocess.run([*py, str(HERE / "plan.py")], capture_output=True, text=True,
                             cwd=HERE.parents[1], env={"PYTHONPATH": str(HERE.parents[1])}).stdout
    rows = []
    for label, (b_old, b_new), (py_old, py_new) in MISTAKES:
        assert B_SOURCE.count(b_old) == 1 and PY_SOURCE.count(py_old) == 1, label
        rows.append({
            "mistake": label,
            "b": outcome(b, B_SOURCE.replace(b_old, b_new), ".bee", b_base),
            "typed_python": outcome(py, "import sys; sys.path.insert(0, %r)\n" % str(HERE.parents[1])
                                    + PY_SOURCE.replace(py_old, py_new), ".py", py_base),
        })
    lines = {"b": sum(1 for l in B_SOURCE.splitlines() if l.strip()),
             "typed_python": sum(1 for l in PY_SOURCE.splitlines() if l.strip())}
    json.dump({"mistakes": rows, "nonblank_lines": lines}, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
