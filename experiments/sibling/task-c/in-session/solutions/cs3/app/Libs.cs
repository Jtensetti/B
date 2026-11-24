using System.Globalization;

namespace App;

/// Port of libs/leadtime (Go): delivery days per supplier.
public static class LeadTime
{
    private static readonly Dictionary<string, int> Days = new(StringComparer.Ordinal)
    {
        ["Nordic Timber"] = 12,
        ["Baltic Steel"] = 9,
        ["Lumo Lighting"] = 5,
        ["Fabrikk AS"] = 7,
        ["Textil Partner"] = 14,
    };

    public static bool TryDays(string supplier, out int days) => Days.TryGetValue(supplier, out days);

    /// Suppliers() in the Go package (sorted).
    public static readonly string[] Suppliers =
        { "Baltic Steel", "Fabrikk AS", "Lumo Lighting", "Nordic Timber", "Textil Partner" };

    /// Closest known supplier name within distance 2 (ties: alphabetically first), or null.
    public static string? Match(string supplier)
    {
        string? best = null;
        int bestDist = int.MaxValue;
        foreach (var name in Suppliers.OrderBy(n => n, StringComparer.Ordinal))
        {
            int d = Levenshtein.Distance(supplier, name);
            if (d < bestDist) { bestDist = d; best = name; }
        }
        return bestDist <= 2 ? best : null;
    }
}

/// Plain Levenshtein distance over UTF-16 code units (same as fastest-levenshtein).
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
                cur[j] = Math.Min(Math.Min(prev[j] + 1, cur[j - 1] + 1), prev[j - 1] + cost);
            }
            (prev, cur) = (cur, prev);
        }
        return prev[b.Length];
    }
}

/// Port of libs/stats (Rust): mean and nearest-rank percentile.
public static class Stats
{
    public static double Mean(double[] values)
    {
        if (values.Length == 0) return 0.0;
        double sum = 0.0;
        foreach (var v in values) sum += v;
        return sum / values.Length;
    }

    /// Mean of the last `window` values (all values when there are fewer); 0.0 for an empty slice.
    public static double TrailingMean(double[] values, long window)
    {
        int n = values.Length;
        int w = (int)Math.Min(Math.Max(window, 1), n);
        if (n == 0) return 0.0;
        return Mean(values[(n - w)..]);
    }

    public static double Percentile(double[] values, double p)
    {
        if (values.Length == 0) return 0.0;
        var v = (double[])values.Clone();
        Array.Sort(v);
        double rankF = Math.Max(Math.Ceiling((p / 100.0) * v.Length), 1.0);
        int rank = (int)rankF;
        return v[Math.Min(rank, v.Length) - 1];
    }
}

/// Port of libs/weeks (Python dates.py): date arithmetic on ISO dates.
public static class Dates
{
    public static DateOnly Parse(string iso) =>
        DateOnly.ParseExact(iso, "yyyy-MM-dd", CultureInfo.InvariantCulture);

    public static string Format(DateOnly d) => d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

    public static string AddDays(string iso, int days) => Format(Parse(iso).AddDays(days));

    /// The date itself on Monday to Friday; the following Monday for a Saturday or Sunday.
    public static string ToWeekday(string iso)
    {
        var d = Parse(iso);
        while (d.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday) d = d.AddDays(1);
        return Format(d);
    }
}
