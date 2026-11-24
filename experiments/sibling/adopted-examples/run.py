"""Measure the registered cases with the b executable supplied as argv[1]."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

PROVIDER = '''raise RuntimeError("provider was imported")

def seconds(minutes: int) -> int:
    return minutes * 60

def kronor(euros: int) -> int:
    return euros * 11

def alert(reading: int) -> bool:
    return reading >= 8
'''
PROGRAM = '''adopt py:provider.seconds as seconds
adopt py:provider.kronor as kronor
adopt py:provider.alert as alert
example seconds(3) == 180
example kronor(7) == 77
example alert(8) == true
print seconds(4)
'''
EDITS = {
    "clean": None,
    "equivalent": ("minutes * 60", "60 * minutes"),
    "unit": ("minutes * 60", "minutes * 60000"),
    "currency": ("euros * 11", "euros * 10"),
    "behavior": ("reading >= 8", "reading > 8"),
    "signature": ("seconds(minutes: int)", "seconds(minutes: int, paid: bool)"),
}


def run(executable):
    results = {}
    for name, edit in EDITS.items():
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp)
            (ws / "provider.py").write_text(PROVIDER.replace(*edit) if edit else PROVIDER)
            (ws / "main.bee").write_text(PROGRAM)
            proc = subprocess.run([executable, "check", "--strict", "main.bee"], cwd=ws,
                                  text=True, capture_output=True, timeout=60)
            results[name] = {"exit": proc.returncode, "diagnostic": proc.stdout + proc.stderr}
    return results


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1]), indent=2))
