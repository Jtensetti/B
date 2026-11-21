import shutil
import io
from contextlib import redirect_stdout
import pytest
from b_lang.compiler import compile_b
from b_lang.runtime import BBoundaryError


@pytest.mark.skipif(shutil.which("dotnet") is None, reason=".NET 10 SDK not installed")
def test_real_dotnet_and_python_interop():
    source = '''use py:statistics as stats
use net:System.Math as Math
let values = [3.0, 4.0, 5.0]
let avg: Float = stats.mean(values)
let hyp: Float = Math.Sqrt(avg * avg + 9.0)
print hyp
'''
    program = compile_b(source, strict=True)
    output = io.StringIO()
    with redirect_stdout(output):
        namespace = {"__name__": "__b_test__"}
        exec(program.code, namespace, namespace)
    assert abs(float(output.getvalue().strip()) - 5.0) < 0.000001


@pytest.mark.skipif(shutil.which("dotnet") is None, reason=".NET 10 SDK not installed")
def test_cross_runtime_text_regex_and_python_statistics():
    source = '''use py:statistics as stats
use net:System.Text.RegularExpressions.Regex as Rx
use net:System.Math as Math
let average: Float = stats.mean([5, 6, 7])
let verified: Bool = Rx.IsMatch("item-42", "^item-[0-9]+$")
let output: Float = if verified then Math.Sqrt(average * average) else 0.0
print output
'''
    program = compile_b(source, strict=True)
    out = io.StringIO()
    with redirect_stdout(out):
        exec(program.code, {"__name__": "__b_test__"})
    assert out.getvalue().strip() == "6.0"
