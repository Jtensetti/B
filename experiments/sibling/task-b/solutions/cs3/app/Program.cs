using System.Diagnostics;
using System.Globalization;
using System.Text;
using System.Text.Json;
using Rules;

// Ports of the team libraries (same logic as their sources in libs/):
//   hours    (Go)     -> HoursParser.Parse
//   quarter  (Rust)   -> Quarter.RoundUp
//   payroll  (Python) -> Withholding.Compute

static class HoursParser
{
    // Mirrors libs/hours/hours.go: "H:MM", minutes 00-59, returns null on error.
    public static double? Parse(string text)
    {
        var parts = text.Trim().Split(':');
        if (parts.Length != 2 || parts[1].Length != 2) return null;
        if (!long.TryParse(parts[0], NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out long h) || h < 0)
            return null;
        if (!long.TryParse(parts[1], NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out long m) || m < 0 || m > 59)
            return null;
        return h + m / 60.0;
    }
}

static class Quarter
{
    // Mirrors libs/quarter/src/lib.rs.
    public static double RoundUp(double hours)
    {
        double quarters = hours * 4.0;
        double tolerance = 4.0 / 3600.0;
        return Math.Max(Math.Ceiling(quarters - tolerance), 0.0) / 4.0;
    }
}

static class Withholding
{
    // Mirrors libs/payroll/withholding.py.
    public static long Compute(double gross, int table)
    {
        double rate = table / 100.0;
        double taxable = Math.Max(0.0, gross - 2000);
        double low = Math.Min(taxable, 48000) * rate;
        double high = Math.Max(0.0, gross - 50000) * (rate + 0.20);
        return (long)Math.Floor(low + high);
    }
}

static class Semver
{
    // Uses the npm semver package from the workspace node_modules, so the behaviour is npm's.
    static string? _semverPath;

    static string SemverPath()
    {
        if (_semverPath is not null) return _semverPath;
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null && !File.Exists(Path.Combine(dir.FullName, "node_modules", "semver", "index.js")))
            dir = dir.Parent;
        if (dir is null) throw new InvalidOperationException("node_modules/semver not found");
        _semverPath = Path.Combine(dir.FullName, "node_modules", "semver", "index.js");
        return _semverPath;
    }

    public static bool Satisfies(string version, string range)
    {
        const string script = "const s=require(process.argv[1]);process.stdout.write(s.satisfies(process.argv[2],process.argv[3])?'1':'0')";
        var psi = new ProcessStartInfo("node")
        {
            RedirectStandardOutput = true,
            UseShellExecute = false,
        };
        psi.ArgumentList.Add("-e");
        psi.ArgumentList.Add(script);
        psi.ArgumentList.Add(SemverPath());
        psi.ArgumentList.Add(version);
        psi.ArgumentList.Add(range);
        using var proc = Process.Start(psi)!;
        string output = proc.StandardOutput.ReadToEnd().Trim();
        proc.WaitForExit();
        return output == "1";
    }
}

static class Program
{
    static string WeekdayName(DateTime d) => d.DayOfWeek switch
    {
        DayOfWeek.Monday => "Mon",
        DayOfWeek.Tuesday => "Tue",
        DayOfWeek.Wednesday => "Wed",
        DayOfWeek.Thursday => "Thu",
        DayOfWeek.Friday => "Fri",
        DayOfWeek.Saturday => "Sat",
        _ => "Sun",
    };

    static int Main()
    {
        string input = Console.In.ReadToEnd();
        using var doc = JsonDocument.Parse(input);
        var root = doc.RootElement;

        var employees = new List<(string Id, double Hourly, int Table)>();
        var employeeIndex = new Dictionary<string, int>(StringComparer.Ordinal);
        foreach (var e in root.GetProperty("employees").EnumerateArray())
        {
            string id = e.GetProperty("id").GetString()!;
            double hourly = e.GetProperty("hourly").GetDouble();
            int table = e.GetProperty("table").GetInt32();
            string contract = e.GetProperty("contract").GetString()!;
            if (Semver.Satisfies(contract, ">=3.0.0")) hourly *= 1.1;
            employeeIndex[id] = employees.Count;
            employees.Add((id, hourly, table));
        }

        string month = root.GetProperty("month").GetString()!;
        var holidays = new HashSet<DateTime>();
        if (root.TryGetProperty("holidays", out var holEl) && holEl.ValueKind == JsonValueKind.Array)
            foreach (var h in holEl.EnumerateArray())
                holidays.Add(DateTime.ParseExact(h.GetString()!, "yyyy-MM-dd", CultureInfo.InvariantCulture).Date);

        var hoursSum = new double[employees.Count];
        var grossSum = new double[employees.Count];
        var rejected = new List<string>();

        foreach (var s in root.GetProperty("shifts").EnumerateArray())
        {
            string shiftId = s.GetProperty("id").GetString()!;
            string empId = s.GetProperty("employee").GetString()!;
            string date = s.GetProperty("date").GetString()!;
            string text = s.GetProperty("hours").GetString()!;

            // Shifts outside the payroll month are ignored: not paid, not rejected.
            if (!date.StartsWith(month + "-", StringComparison.Ordinal)) continue;

            if (!employeeIndex.TryGetValue(empId, out int idx))
            {
                rejected.Add(shiftId);
                continue;
            }
            double? parsed = HoursParser.Parse(text);
            if (parsed is null)
            {
                rejected.Add(shiftId);
                continue;
            }

            double worked = parsed.Value;
            if (s.TryGetProperty("break", out var breakEl) && breakEl.ValueKind == JsonValueKind.String)
            {
                double? brk = HoursParser.Parse(breakEl.GetString()!);
                if (brk is null || brk.Value > worked)
                {
                    rejected.Add(shiftId);
                    continue;
                }
                worked -= brk.Value;
            }

            double hours = Quarter.RoundUp(worked);
            var day = DateTime.ParseExact(date, "yyyy-MM-dd", CultureInfo.InvariantCulture);
            double multiplier = holidays.Contains(day.Date) ? Overtime.Holiday() : Overtime.Multiplier(WeekdayName(day));

            hoursSum[idx] += hours;
            grossSum[idx] += hours * employees[idx].Hourly * multiplier;
        }

        rejected.Sort(StringComparer.Ordinal);

        var sb = new StringBuilder();
        sb.Append("{\"payslips\":{");
        for (int i = 0; i < employees.Count; i++)
        {
            var emp = employees[i];
            double gross = Math.Round(grossSum[i], 2, MidpointRounding.AwayFromZero);
            long tax = Withholding.Compute(gross, emp.Table);
            double net = gross - tax;
            if (i > 0) sb.Append(',');
            sb.Append(JsonSerializer.Serialize(emp.Id)).Append(":{");
            sb.Append("\"hours\":").Append(Num(hoursSum[i])).Append(',');
            sb.Append("\"gross\":").Append(Num(gross)).Append(',');
            sb.Append("\"tax\":").Append(tax).Append(',');
            sb.Append("\"net\":").Append(Num(net)).Append(',');
            double pension = Math.Round(gross * 0.045, 2, MidpointRounding.AwayFromZero);
            sb.Append("\"pension\":").Append(Num(pension));
            sb.Append('}');
        }
        sb.Append("},\"rejected\":[");
        for (int i = 0; i < rejected.Count; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append(JsonSerializer.Serialize(rejected[i]));
        }
        sb.Append("]}");

        Console.Out.WriteLine(sb.ToString());
        return 0;
    }

    static string Num(double v) => v.ToString("R", CultureInfo.InvariantCulture);
}
