"""C# as a relative: public static methods read by .NET reflection, calls across JSON lines."""
import io
import shutil
from contextlib import redirect_stdout

import pytest

from b_lang.compiler import compile_b
from b_lang.runtime import ForeignError
from b_lang.types import BError

pytestmark = pytest.mark.skipif(shutil.which("dotnet") is None, reason=".NET SDK not installed")

PROJECT = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
'''
SOURCE = '''namespace Tax;

public static class Vat
{
    static readonly Dictionary<string, double> Rates = new() { ["SE"] = 0.25, ["DE"] = 0.19 };
    public static double Rate(string country) =>
        Rates.TryGetValue(country, out var r) ? r : throw new KeyNotFoundException("no VAT rate for " + country);
    public static double[] AddVat(double[] nets, string country) => nets.Select(n => Math.Round(n * (1 + Rate(country)), 2)).ToArray();
    public static Dictionary<string, int> Lengths(List<string> words) => words.ToDictionary(w => w, w => w.Length);
    public static int? Find(int[] xs, int x) { var i = Array.IndexOf(xs, x); return i < 0 ? null : i; }
    public static double Over(double a) => a;
    public static double Over(double a, double b) => a + b;
}
'''


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    root = tmp_path_factory.mktemp("csprog")
    (root / "Tax").mkdir()
    (root / "Tax" / "Tax.csproj").write_text(PROJECT)
    (root / "Tax" / "Vat.cs").write_text(SOURCE)
    return root


@pytest.fixture
def program_dir(project, monkeypatch):
    monkeypatch.setenv("B_PROGRAM_DIR", str(project))


def run(source):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exec(compile_b(source, strict=True).code, {"__name__": "__b_test__"})
    return buffer.getvalue().splitlines()


def test_a_local_project_is_typed_by_reflection(program_dir):
    assert run('use cs:"./Tax" as tax\n'
               'print to_json(tax.Vat.AddVat([100.0, 80.0], "DE"))\n'
               'print to_json(tax.Vat.Lengths(["ab", "cde"]))\n'
               'print tax.Vat.Find([3, 5, 7], 7) ?? -1\nprint tax.Vat.Find([3], 9) ?? -1\n') == [
        "[119.0, 95.2]", '{"ab": 2, "cde": 3}', "2", "-1"]


def test_an_exception_becomes_none_when_declared(program_dir):
    assert run('use cs:"./Tax" as tax\nforeign tax.Vat.Rate(Text) -> Option[Float] on error\n'
               'print to_json([tax.Vat.Rate(c) ?? 0.0 for c in ["SE", "NO"]])\n') == ["[0.25, 0.0]"]
    with pytest.raises(ForeignError):
        run('use cs:"./Tax" as tax\nprint tax.Vat.Rate("NO")\n')


@pytest.mark.parametrize(("source", "fragment"), [
    ('use cs:"./Tax" as tax\nlet x: Text = tax.Vat.Rate("SE")\n', "expected Text, got Float"),
    ('use cs:"./Tax" as tax\nprint tax.Vat.Over(1.0)\n', "overloaded"),
    ('use cs:"Newtonsoft.Json" as j\n', "only local C# projects"),
])
def test_mistakes_at_the_csharp_border_are_compile_errors(program_dir, source, fragment):
    with pytest.raises(BError) as exc:
        compile_b(source, strict=True)
    assert fragment in exc.value.message
