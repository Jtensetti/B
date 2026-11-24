using System.Globalization;

namespace App;

/// Port of libs/calendar/workdays.py: Swedish working days.
public static class Workdays
{
    static readonly HashSet<string> Holidays2026 = new()
    {
        "2026-01-01", "2026-01-06", "2026-04-03", "2026-04-06", "2026-05-01", "2026-05-14",
        "2026-06-06", "2026-06-19", "2026-12-24", "2026-12-25", "2026-12-26", "2026-12-31",
    };

    /// True for Monday to Friday that is not a Swedish public holiday.
    public static bool IsWorkday(string isoDate) =>
        IsWorkday(DateOnly.ParseExact(isoDate, "yyyy-MM-dd", CultureInfo.InvariantCulture));

    static bool IsWorkday(DateOnly d) =>
        d.DayOfWeek != DayOfWeek.Saturday && d.DayOfWeek != DayOfWeek.Sunday
        && !Holidays2026.Contains(d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));

    /// The first working day strictly after the given ISO date.
    public static string NextWorkday(string isoDate)
    {
        var d = DateOnly.ParseExact(isoDate, "yyyy-MM-dd", CultureInfo.InvariantCulture).AddDays(1);
        while (!IsWorkday(d)) d = d.AddDays(1);
        return d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    }
}
