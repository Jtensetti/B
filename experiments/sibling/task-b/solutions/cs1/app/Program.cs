using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using System.Text.Json.Nodes;
using Rules;

var root = FindWorkspaceRoot(AppContext.BaseDirectory);

var top = JsonDocument.Parse(Console.In.ReadToEnd()).RootElement;

// Employees in input order. A repeated id keeps its last definition.
var employeeOrder = new List<string>();
var employees = new Dictionary<string, (decimal Hourly, int Table, string Contract)>(StringComparer.Ordinal);
foreach (var e in top.GetProperty("employees").EnumerateArray())
{
    var id = e.GetProperty("id").GetString()!;
    if (!employees.ContainsKey(id)) employeeOrder.Add(id);
    employees[id] = (e.GetProperty("hourly").GetDecimal(), e.GetProperty("table").GetInt32(), e.GetProperty("contract").GetString()!);
}

// Contract versions in the ">=3.0.0" range (npm semver) get a 10 % higher hourly rate.
var contractMatches = ContractSatisfies(employeeOrder.Select(id => employees[id].Contract).ToArray(), root);
var rateByEmp = new Dictionary<string, decimal>(StringComparer.Ordinal);
for (int i = 0; i < employeeOrder.Count; i++)
    rateByEmp[employeeOrder[i]] = employees[employeeOrder[i]].Hourly * (contractMatches[i] ? 1.1m : 1m);

var monthText = top.GetProperty("month").GetString()!;
var payMonth = DateOnly.ParseExact(monthText + "-01", "yyyy-MM-dd", CultureInfo.InvariantCulture);

// Public holidays (optional). A shift on one of these pays Overtime.Holiday().
var holidays = new HashSet<DateOnly>();
if (top.TryGetProperty("holidays", out var hol) && hol.ValueKind == JsonValueKind.Array)
{
    foreach (var h in hol.EnumerateArray())
        if (h.ValueKind == JsonValueKind.String
            && DateOnly.TryParseExact(h.GetString(), "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var hd))
            holidays.Add(hd);
}

var rejected = new List<string>();
var candidates = new List<(string Id, string Employee, DateOnly Date, string Hours, string? Break)>();
foreach (var s in top.GetProperty("shifts").EnumerateArray())
{
    var id = s.GetProperty("id").GetString()!;
    var emp = s.GetProperty("employee").GetString()!;
    var dateText = s.GetProperty("date").GetString()!;
    var hoursText = s.GetProperty("hours").GetString()!;
    var breakText = s.TryGetProperty("break", out var b) && b.ValueKind == JsonValueKind.String ? b.GetString() : null;
    if (!DateOnly.TryParseExact(dateText, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out var date))
    {
        rejected.Add(id);
        continue;
    }
    // Shifts dated outside the payslip month are ignored, not rejected.
    if (date.Year != payMonth.Year || date.Month != payMonth.Month) continue;
    if (!employees.ContainsKey(emp))
    {
        rejected.Add(id);
        continue;
    }
    candidates.Add((id, emp, date, hoursText, breakText));
}

// Parse all durations in one call to the Go library.
var parsed = ParseHours(candidates.Select(c => c.Hours).ToArray(), root);

// Parse the breaks that are present, again in one call.
var withBreak = Enumerable.Range(0, candidates.Count).Where(i => parsed[i] is not null && candidates[i].Break is not null).ToArray();
var parsedBreaks = ParseHours(withBreak.Select(i => candidates[i].Break!).ToArray(), root);
var breakByIndex = new Dictionary<int, double?>();
for (int k = 0; k < withBreak.Length; k++) breakByIndex[withBreak[k]] = parsedBreaks[k];

var accepted = new List<(string Id, string Employee, DateOnly Date, double Hours)>();
for (int i = 0; i < candidates.Count; i++)
{
    var c = candidates[i];
    if (parsed[i] is null) { rejected.Add(c.Id); continue; }
    var worked = parsed[i]!.Value;
    if (c.Break is not null)
    {
        var brk = breakByIndex[i];
        if (brk is null || brk.Value > worked) { rejected.Add(c.Id); continue; }
        worked -= brk.Value;
    }
    accepted.Add((c.Id, c.Employee, c.Date, worked));
}

// Round every accepted shift up to the quarter hour in one call to the Rust library.
var rounded = RoundUp(accepted.Select(a => a.Hours).ToArray(), root);

var hoursByEmp = new Dictionary<string, double>(StringComparer.Ordinal);
var grossByEmp = new Dictionary<string, decimal>(StringComparer.Ordinal);
for (int i = 0; i < accepted.Count; i++)
{
    var a = accepted[i];
    var hourly = rateByEmp[a.Employee];
    var weekday = a.Date.DayOfWeek.ToString().Substring(0, 3);
    var multiplier = (decimal)(holidays.Contains(a.Date) ? Overtime.Holiday() : Overtime.Multiplier(weekday));
    var h = rounded[i];
    hoursByEmp[a.Employee] = (hoursByEmp.TryGetValue(a.Employee, out var sh) ? sh : 0.0) + h;
    grossByEmp[a.Employee] = (grossByEmp.TryGetValue(a.Employee, out var sg) ? sg : 0m) + (decimal)h * hourly * multiplier;
}

// Withholding for every employee, in one call to the Python library.
var grossRounded = employeeOrder.Select(id => Math.Round(grossByEmp.GetValueOrDefault(id), 2, MidpointRounding.AwayFromZero)).ToArray();
var taxes = Withholding(
    grossRounded.Select((g, i) => (g, employees[employeeOrder[i]].Table)).ToArray(), root);

var payslips = new JsonObject();
for (int i = 0; i < employeeOrder.Count; i++)
{
    var id = employeeOrder[i];
    var gross = grossRounded[i];
    var tax = taxes[i];
    payslips[id] = new JsonObject
    {
        ["hours"] = hoursByEmp.GetValueOrDefault(id),
        ["gross"] = (double)gross,
        ["tax"] = tax,
        ["net"] = (double)(gross - tax),
        ["pension"] = (double)Math.Round(gross * 0.045m, 2, MidpointRounding.AwayFromZero),
    };
}

rejected.Sort(StringComparer.Ordinal);
var result = new JsonObject
{
    ["payslips"] = payslips,
    ["rejected"] = new JsonArray(rejected.Select(r => (JsonNode)JsonValue.Create(r)!).ToArray()),
};
Console.Out.WriteLine(result.ToJsonString());

static string FindWorkspaceRoot(string start)
{
    for (var dir = new DirectoryInfo(start); dir != null; dir = dir.Parent)
    {
        if (Directory.Exists(Path.Combine(dir.FullName, "libs"))
            && File.Exists(Path.Combine(dir.FullName, "app", "App.csproj")))
            return dir.FullName;
    }
    throw new DirectoryNotFoundException("workspace root not found above " + start);
}

static string Run(string file, string[] args, string workDir, string input)
{
    var psi = new ProcessStartInfo(file)
    {
        WorkingDirectory = workDir,
        RedirectStandardInput = true,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        UseShellExecute = false,
    };
    foreach (var a in args) psi.ArgumentList.Add(a);
    psi.Environment["GOTOOLCHAIN"] = "local";
    using var p = Process.Start(psi) ?? throw new InvalidOperationException("cannot start " + file);
    var stdoutTask = p.StandardOutput.ReadToEndAsync();
    var stderrTask = p.StandardError.ReadToEndAsync();
    p.StandardInput.Write(input);
    p.StandardInput.Close();
    p.WaitForExit();
    var stdout = stdoutTask.Result;
    var stderr = stderrTask.Result;
    if (p.ExitCode != 0) throw new InvalidOperationException($"{file} exited {p.ExitCode}: {stderr}");
    return stdout;
}

static double?[] ParseHours(string[] texts, string root)
{
    if (texts.Length == 0) return [];
    var json = JsonSerializer.Serialize(texts);
    var output = Run("go", ["run", "."], Path.Combine(root, "app", "tools", "hours"), json);
    using var doc = JsonDocument.Parse(output);
    return doc.RootElement.EnumerateArray()
        .Select(e => e.ValueKind == JsonValueKind.Null ? (double?)null : e.GetDouble())
        .ToArray();
}

static double[] RoundUp(double[] hours, string root)
{
    if (hours.Length == 0) return [];
    var input = string.Concat(hours.Select(h => h.ToString("R", CultureInfo.InvariantCulture) + "\n"));
    var output = Run("cargo", ["run", "-q", "--release"], Path.Combine(root, "app", "tools", "quarter"), input);
    return output.Split('\n', StringSplitOptions.RemoveEmptyEntries)
        .Select(l => double.Parse(l, CultureInfo.InvariantCulture))
        .ToArray();
}

static bool[] ContractSatisfies(string[] versions, string root)
{
    if (versions.Length == 0) return [];
    var output = Run("node", [Path.Combine(root, "app", "tools", "semver", "semver_helper.js"),
        Path.Combine(root, "node_modules", "semver"), ">=3.0.0"], root, JsonSerializer.Serialize(versions));
    using var doc = JsonDocument.Parse(output);
    return doc.RootElement.EnumerateArray().Select(e => e.GetBoolean()).ToArray();
}

static int[] Withholding((decimal Gross, int Table)[] items, string root)
{
    if (items.Length == 0) return [];
    var input = string.Concat(items.Select(i =>
        i.Gross.ToString("R", CultureInfo.InvariantCulture) + " " + i.Table.ToString(CultureInfo.InvariantCulture) + "\n"));
    var payroll = Path.Combine(root, "libs", "payroll");
    var output = Run("python3", [Path.Combine(root, "app", "tools", "payroll", "tax_helper.py"), payroll], payroll, input);
    return output.Split('\n', StringSplitOptions.RemoveEmptyEntries)
        .Select(l => int.Parse(l, CultureInfo.InvariantCulture))
        .ToArray();
}
