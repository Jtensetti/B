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
