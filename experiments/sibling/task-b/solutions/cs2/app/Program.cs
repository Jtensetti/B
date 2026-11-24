using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using Rules;

// Monthly payslips. Reads one JSON line from stdin, writes one JSON line to stdout.
// Hours parsing, quarter rounding and withholding are done by the libraries in libs/ (Go, Rust, Python),
// run as helper processes with one batch per library. Overtime multipliers come from the Rules project.

var InOpts = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
var OutOpts = new JsonSerializerOptions
{
    PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
    Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
};

var ws = FindWorkspace();
var input = JsonSerializer.Deserialize<PayrollInput>(Console.In.ReadToEnd(), InOpts)
    ?? throw new InvalidOperationException("empty input");

var employees = new Dictionary<string, Employee>(StringComparer.Ordinal);
foreach (var e in input.Employees) employees.TryAdd(e.Id, e);

var rejected = new List<string>();
var candidates = new List<Shift>();
// Only shifts dated in the payslip month count. Shifts from other months are ignored, not rejected.
foreach (var s in input.Shifts)
{
    if (!s.Date.StartsWith(input.Month + "-", StringComparison.Ordinal)) continue;
    if (employees.ContainsKey(s.Employee)) candidates.Add(s);
    else rejected.Add(s.Id);
}

// Worked time = Parse(hours) - Parse(break). A missing break counts as 0.
var texts = new List<string>();
foreach (var s in candidates)
{
    texts.Add(s.Hours);
    if (s.Break is not null) texts.Add(s.Break);
}
var parsed = ParseHours(ws, texts);
var valid = new List<Shift>();
var validHours = new List<double>();
int k = 0;
foreach (var s in candidates)
{
    var hours = parsed[k++];
    double? breakHours = 0;
    if (s.Break is not null) breakHours = parsed[k++];
    if (hours is double h && breakHours is double b && b <= h)
    {
        valid.Add(s);
        validHours.Add(h - b);
    }
    else rejected.Add(s.Id);
}

var rounded = RoundUp(ws, validHours);

// Contracts at or above 3.0.0 (npm semver rules, so prereleases of 3.0.0 are excluded) get 10 % more per hour.
var employeeList = employees.Values.ToList();
var raised = SemverSatisfies(ws, employeeList.Select(e => e.Contract).ToList(), ">=3.0.0");
var rateBy = new Dictionary<string, double>(StringComparer.Ordinal);
for (int i = 0; i < employeeList.Count; i++)
    rateBy[employeeList[i].Id] = employeeList[i].Hourly * (raised[i] ? 1.10 : 1.0);

// A shift on a public holiday pays the holiday multiplier instead of the weekday one.
var holidays = new HashSet<string>(input.Holidays, StringComparer.Ordinal);

var hoursBy = new Dictionary<string, double>(StringComparer.Ordinal);
var grossBy = new Dictionary<string, double>(StringComparer.Ordinal);
foreach (var id in employees.Keys)
{
    hoursBy[id] = 0;
    grossBy[id] = 0;
}
for (int i = 0; i < valid.Count; i++)
{
    var shift = valid[i];
    var emp = employees[shift.Employee];
    double hours = rounded[i];
    double multiplier = holidays.Contains(shift.Date)
        ? Overtime.Holiday()
        : Overtime.Multiplier(WeekdayName(shift.Date));
    hoursBy[emp.Id] += hours;
    grossBy[emp.Id] += hours * rateBy[emp.Id] * multiplier;
}

var ids = employees.Keys.ToList();
var grossRounded = ids.Select(id => Math.Round(grossBy[id], 2, MidpointRounding.AwayFromZero)).ToList();
var taxes = Withholding(ws, ids.Select((id, i) => (grossRounded[i], employees[id].Table)).ToList());

var payslips = new Dictionary<string, Slip>(StringComparer.Ordinal);
for (int i = 0; i < ids.Count; i++)
{
    var id = ids[i];
    long tax = taxes[i];
    double gross = grossRounded[i];
    // Employer-paid pension: 4.5 % of gross. It does not change tax or net.
    double pension = Math.Round(gross * 0.045, 2, MidpointRounding.AwayFromZero);
    payslips[id] = new Slip(hoursBy[id], gross, tax, Math.Round(gross - tax, 2, MidpointRounding.AwayFromZero), pension);
}

rejected.Sort(StringComparer.Ordinal);
Console.WriteLine(JsonSerializer.Serialize(new Result(payslips, rejected), OutOpts));

// ---- helpers ----

static string WeekdayName(string date) =>
    DateOnly.ParseExact(date, "yyyy-MM-dd", CultureInfo.InvariantCulture).DayOfWeek.ToString()[..3];

// Hours text -> hours, or null where hours.Parse fails. One batch to the Go helper.
static List<double?> ParseHours(string ws, List<string> texts)
{
    var result = new List<double?>();
    if (texts.Count == 0) return result;
    var lines = string.Join("\n", texts.Select(t => JsonSerializer.Serialize(t))) + "\n";
    var rows = RunTool("go", new[] { "run", "." }, Path.Combine(ws, "app", "helpers", "hours"), lines);
    var outLines = SplitLines(rows, texts.Count);
    foreach (var row in outLines)
        result.Add(row == "ERR" ? null : double.Parse(row, CultureInfo.InvariantCulture));
    return result;
}

// Hours -> quarter-hour rounded hours. One batch to the Rust helper.
static List<double> RoundUp(string ws, List<double> hours)
{
    var result = new List<double>();
    if (hours.Count == 0) return result;
    var lines = string.Join("\n", hours.Select(h => h.ToString("R", CultureInfo.InvariantCulture))) + "\n";
    var rows = RunTool("cargo", new[] { "run", "--quiet", "--manifest-path", Path.Combine(ws, "app", "helpers", "quarter", "Cargo.toml") }, ws, lines);
    foreach (var row in SplitLines(rows, hours.Count))
        result.Add(double.Parse(row, CultureInfo.InvariantCulture));
    return result;
}

// (version, range) -> whether npm semver says the version satisfies the range. One batch to node.
static List<bool> SemverSatisfies(string ws, List<string> versions, string range)
{
    var result = new List<bool>();
    if (versions.Count == 0) return result;
    var lines = string.Join("\n", versions.Select(v => JsonSerializer.Serialize(new object[] { v, range }))) + "\n";
    var rows = RunTool("node", new[] { Path.Combine(ws, "app", "helpers", "semver", "satisfies.js"), ws }, ws, lines);
    foreach (var row in SplitLines(rows, versions.Count))
        result.Add(row == "true");
    return result;
}

// (gross, table) -> tax in whole kronor. One batch to the Python withholding module.
static List<long> Withholding(string ws, List<(double Gross, int Table)> items)
{
    var result = new List<long>();
    if (items.Count == 0) return result;
    var libDir = Path.Combine(ws, "libs", "payroll");
    var code = "import json, sys\n" +
               "sys.path.insert(0, sys.argv[1])\n" +
               "from withholding import withholding\n" +
               "for line in sys.stdin:\n" +
               "    gross, table = json.loads(line)\n" +
               "    print(withholding(float(gross), int(table)))\n";
    var lines = string.Join("\n", items.Select(i => JsonSerializer.Serialize(new object[] { i.Gross, i.Table }))) + "\n";
    var rows = RunTool("python3", new[] { "-I", "-B", "-c", code, libDir }, ws, lines);
    foreach (var row in SplitLines(rows, items.Count))
        result.Add(long.Parse(row, CultureInfo.InvariantCulture));
    return result;
}

static string[] SplitLines(string text, int expected)
{
    var rows = text.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
    if (rows.Length != expected)
        throw new InvalidOperationException($"helper returned {rows.Length} lines, expected {expected}");
    return rows;
}

static string RunTool(string file, string[] args, string workDir, string stdinText)
{
    var psi = new ProcessStartInfo(file)
    {
        RedirectStandardInput = true,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        UseShellExecute = false,
        WorkingDirectory = workDir,
        StandardInputEncoding = new UTF8Encoding(false),
        StandardOutputEncoding = Encoding.UTF8,
        StandardErrorEncoding = Encoding.UTF8,
    };
    foreach (var a in args) psi.ArgumentList.Add(a);
    using var p = Process.Start(psi) ?? throw new InvalidOperationException("cannot start " + file);
    var stdoutTask = p.StandardOutput.ReadToEndAsync();
    var stderrTask = p.StandardError.ReadToEndAsync();
    p.StandardInput.Write(stdinText);
    p.StandardInput.Close();
    p.WaitForExit();
    var stdout = stdoutTask.Result;
    var stderr = stderrTask.Result;
    if (p.ExitCode != 0)
        throw new InvalidOperationException($"{file} exited with {p.ExitCode}: {stderr}");
    return stdout;
}

// Walks up from the executable (and the current directory) to the workspace, which holds libs/.
static string FindWorkspace()
{
    foreach (var start in new[] { AppContext.BaseDirectory, Directory.GetCurrentDirectory() })
    {
        var dir = new DirectoryInfo(start);
        while (dir != null)
        {
            if (Directory.Exists(Path.Combine(dir.FullName, "libs")) && Directory.Exists(Path.Combine(dir.FullName, "app")))
                return dir.FullName;
            dir = dir.Parent;
        }
    }
    throw new DirectoryNotFoundException("workspace with libs/ and app/ not found");
}

public sealed class Employee
{
    public string Id { get; set; } = "";
    public double Hourly { get; set; }
    public int Table { get; set; }
    public string Contract { get; set; } = "";
}

public sealed class Shift
{
    public string Id { get; set; } = "";
    public string Employee { get; set; } = "";
    public string Date { get; set; } = "";
    public string Hours { get; set; } = "";
    public string? Break { get; set; }
}

public sealed class PayrollInput
{
    public string Month { get; set; } = "";
    public List<Employee> Employees { get; set; } = new();
    public List<Shift> Shifts { get; set; } = new();
    public List<string> Holidays { get; set; } = new();
}

public sealed record Slip(double Hours, double Gross, long Tax, double Net, double Pension);

public sealed record Result(Dictionary<string, Slip> Payslips, List<string> Rejected);
