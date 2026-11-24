// C# ports of the other teams' libraries (Go, Rust, Python), following their code.
using System.Globalization;

namespace Reorder;

/// Port of libs/leadtime (Go): delivery days per supplier.
public static class Leadtime
{
    private static readonly Dictionary<string, int> Days = new(StringComparer.Ordinal)
    {
        ["Nordic Timber"] = 12,
        ["Baltic Steel"] = 9,
        ["Lumo Lighting"] = 5,
        ["Fabrikk AS"] = 7,
        ["Textil Partner"] = 14,
    };

    public static IEnumerable<string> Suppliers() => Days.Keys.OrderBy(k => k, StringComparer.Ordinal);

    public static bool TryDays(string supplier, out int days) => Days.TryGetValue(supplier, out days);

    /// Matches a misspelled supplier to the closest known name (distance <= 2, ties alphabetical).
    /// Returns null when no name is close enough.
    public static string? Resolve(string supplier)
    {
        string? best = null;
        int bestDist = int.MaxValue;
        foreach (var name in Suppliers())
        {
            int d = Levenshtein.Distance(supplier, name);
            if (d < bestDist) { bestDist = d; best = name; }
        }
        return bestDist <= 2 ? best : null;
    }
}

/// Standard Levenshtein edit distance (insert, delete, substitute).
public static class Levenshtein
{
    public static int Distance(string a, string b)
    {
        var prev = new int[b.Length + 1];
        var cur = new int[b.Length + 1];
        for (int j = 0; j <= b.Length; j++) prev[j] = j;
        for (int i = 1; i <= a.Length; i++)
        {
            cur[0] = i;
            for (int j = 1; j <= b.Length; j++)
            {
                int cost = a[i - 1] == b[j - 1] ? 0 : 1;
                cur[j] = Math.Min(Math.Min(cur[j - 1] + 1, prev[j] + 1), prev[j - 1] + cost);
            }
            (prev, cur) = (cur, prev);
        }
        return prev[b.Length];
    }
}

/// Port of libs/stats (Rust): mean, trailing mean and nearest-rank percentile.
public static class Stats
{
    public static double Mean(double[] values)
    {
        if (values.Length == 0) return 0.0;
        double sum = 0.0;
        foreach (var v in values) sum += v;
        return sum / values.Length;
    }

    /// Mean of the last `window` values (all when fewer); 0.0 for an empty slice.
    public static double TrailingMean(double[] values, long window)
    {
        int n = values.Length;
        if (n == 0) return 0.0;
        int w = (int)Math.Min(Math.Max(window, 1), n);
        var tail = new double[w];
        Array.Copy(values, n - w, tail, 0, w);
        return Mean(tail);
    }

    public static double Percentile(double[] values, double p)
    {
        if (values.Length == 0) return 0.0;
        var v = (double[])values.Clone();
        Array.Sort(v);
        int rank = (int)Math.Max(Math.Ceiling((p / 100.0) * v.Length), 1.0);
        return v[Math.Min(rank, v.Length) - 1];
    }
}

/// Port of libs/weeks (Python): date arithmetic on ISO dates.
public static class Dates
{
    public const string Format = "yyyy-MM-dd";

    public static DateOnly Parse(string iso) => DateOnly.ParseExact(iso, Format, CultureInfo.InvariantCulture);

    public static string AddDays(string isoDate, int days) =>
        Parse(isoDate).AddDays(days).ToString(Format, CultureInfo.InvariantCulture);

    /// Port of to_weekday: the date itself on Mon-Fri, else the following Monday.
    public static string ToWeekday(string isoDate)
    {
        var d = Parse(isoDate);
        while (d.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday) d = d.AddDays(1);
        return d.ToString(Format, CultureInfo.InvariantCulture);
    }

    /// The ISO week number (1-53) of a date, as iso_week.
    public static int IsoWeek(DateOnly date) =>
        ISOWeek.GetWeekOfYear(date.ToDateTime(TimeOnly.MinValue));
}
