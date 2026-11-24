// C# ports of the team libraries in ../libs (behaviour follows their source).
using System.Globalization;

namespace App;

// libs/leadtime (Go): Days and Suppliers.
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

    public static bool TryDays(string supplier, out int days) => Days.TryGetValue(supplier, out days);

    public static IReadOnlyList<string> Suppliers() =>
        new[] { "Baltic Steel", "Fabrikk AS", "Lumo Lighting", "Nordic Timber", "Textil Partner" };
}

// Levenshtein edit distance (as in fastest-levenshtein's distance).
public static class Edit
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

// libs/stats (Rust): mean, percentile, trailing_mean.
public static class Stats
{
    public static double Mean(double[] values)
    {
        if (values.Length == 0) return 0.0;
        double sum = 0.0;
        foreach (var v in values) sum += v;
        return sum / values.Length;
    }

    // Nearest rank on the sorted values, p in 0..=100.
    public static double Percentile(double[] values, double p)
    {
        if (values.Length == 0) return 0.0;
        var v = (double[])values.Clone();
        Array.Sort(v);
        int rank = (int)Math.Max(Math.Ceiling((p / 100.0) * v.Length), 1.0);
        return v[Math.Min(rank, v.Length) - 1];
    }

    public static double TrailingMean(double[] values, long window)
    {
        int n = values.Length;
        int w = (int)Math.Min(Math.Max(window, 1), n);
        if (n == 0) return 0.0;
        return Mean(values[(n - w)..]);
    }
}

// libs/weeks (Python dates.py): add_days, iso_week, to_weekday.
public static class Dates
{
    public const string Format = "yyyy-MM-dd";

    public static DateOnly Parse(string iso) =>
        DateOnly.ParseExact(iso, Format, CultureInfo.InvariantCulture);

    public static string Format1(DateOnly d) => d.ToString(Format, CultureInfo.InvariantCulture);

    public static string AddDays(string isoDate, int days) => Format1(Parse(isoDate).AddDays(days));

    // The date itself on Monday to Friday; the following Monday for a Saturday or Sunday.
    public static DateOnly ToWeekday(DateOnly d)
    {
        while (d.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday) d = d.AddDays(1);
        return d;
    }

    // ISO week number (1-53) of a date.
    public static int IsoWeek(DateOnly d) =>
        ISOWeek.GetWeekOfYear(d.ToDateTime(TimeOnly.MinValue));
}
