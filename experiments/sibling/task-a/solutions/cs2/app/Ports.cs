// C# ports of the non-C# libraries in libs/ (behaviour copied from their sources).
namespace App;

/// Port of libs/tariff (Go).
public static class Tariff
{
    static readonly Dictionary<string, int> Zones = new()
    {
        ["SE"] = 1, ["NO"] = 2, ["DK"] = 2, ["FI"] = 2, ["DE"] = 3, ["NL"] = 3, ["PL"] = 3,
        ["FR"] = 4, ["ES"] = 4, ["IT"] = 4,
    };
    static readonly Dictionary<int, double> Start = new() { [1] = 49, [2] = 79, [3] = 99, [4] = 129 };
    static readonly Dictionary<int, double> PerKg = new() { [1] = 6.5, [2] = 9.0, [3] = 11.0, [4] = 14.5 };

    public static bool TryZone(string country, out int zone) =>
        Zones.TryGetValue(country.Trim().ToUpperInvariant(), out zone);

    /// Carrier price in SEK excluding VAT; weight rounded up to the next half kilogram.
    public static double BasePrice(int zone, double weightKg)
    {
        double billed = Math.Ceiling(weightKg * 2) / 2;
        return Start[zone] + PerKg[zone] * billed;
    }
}

/// Port of libs/geo (Rust).
public static class Geo
{
    const double EarthRadiusKm = 6371.0;

    static double Rad(double deg) => deg * (Math.PI / 180.0);

    public static double DistanceKm(double lat1, double lon1, double lat2, double lon2)
    {
        double p1 = Rad(lat1), p2 = Rad(lat2);
        double dp = Rad(lat2 - lat1);
        double dl = Rad(lon2 - lon1);
        double s1 = Math.Sin(dp / 2.0), s2 = Math.Sin(dl / 2.0);
        double a = s1 * s1 + Math.Cos(p1) * Math.Cos(p2) * (s2 * s2);
        return 2.0 * EarthRadiusKm * Math.Asin(Math.Sqrt(a));
    }

    /// Road distance estimate: great-circle distance times 1.25.
    public static double RoadKm(double lat1, double lon1, double lat2, double lon2) =>
        DistanceKm(lat1, lon1, lat2, lon2) * 1.25;
}

/// Port of libs/calendar/workdays.py (Python).
public static class Calendar
{
    static readonly HashSet<string> Holidays2026 = new()
    {
        "2026-01-01", "2026-01-06", "2026-04-03", "2026-04-06", "2026-05-01", "2026-05-14",
        "2026-06-06", "2026-06-19", "2026-12-24", "2026-12-25", "2026-12-26", "2026-12-31",
    };

    /// True for a working day given as an ISO date string (see IsWorkday(DateOnly)).
    public static bool IsWorkday(string isoDate) =>
        IsWorkday(DateOnly.ParseExact(isoDate, "yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture));

    public static bool IsWorkday(DateOnly d)
    {
        var iso = d.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
        bool weekday = d.DayOfWeek != DayOfWeek.Saturday && d.DayOfWeek != DayOfWeek.Sunday;
        return weekday && !Holidays2026.Contains(iso);
    }

    /// First working day strictly after the given ISO date.
    public static string NextWorkday(string isoDate)
    {
        var d = DateOnly.ParseExact(isoDate, "yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture).AddDays(1);
        while (!IsWorkday(d)) d = d.AddDays(1);
        return d.ToString("yyyy-MM-dd", System.Globalization.CultureInfo.InvariantCulture);
    }
}

/// Port of fastest-levenshtein distance (node_modules): plain unit-cost Levenshtein.
public static class Lev
{
    public static int Distance(string a, string b)
    {
        if (a.Length == 0) return b.Length;
        if (b.Length == 0) return a.Length;
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
