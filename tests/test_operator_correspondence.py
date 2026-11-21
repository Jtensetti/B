"""Replay the signed-grid experiment with the actual Python and .NET runtimes."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(shutil.which("dotnet") is None, reason=".NET SDK unavailable")
def test_same_glyph_and_unlisted_remainder_convention():
    script = Path(__file__).resolve().parents[1] / "experiments/operator-correspondence/compare.py"
    report = json.loads(subprocess.check_output([sys.executable, str(script)], text=True))
    positive = report["positive only"]
    grid = report["signed grid"]
    assert positive["cases"] == positive["same_remainder_B_and_Csharp"] == 72
    assert all(len(models) == 3 for models in positive["remaining_remainder_models"].values())
    assert grid["cases"] == grid["same_sign_all_three"] == 300
    assert grid["same_remainder_B_and_Csharp"] == 214
    assert grid["remaining_remainder_models"] == {
        "B": ["floor"], "Python": ["floor"], "C#": ["truncate"]
    }
    for language, probe in report["automatically selected probes"].items():
        assert len(probe["queries"]) == 2
        assert probe["survivors"] == grid["remaining_remainder_models"][language]
    outside = report["unlisted rule (math.remainder)"]
    assert outside["survivors"] == ["truncate"]
    assert outside["validation"]["truncate"]["mismatches"] == 80
