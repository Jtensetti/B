namespace App;

/// Port of libs/tariff (Go): carrier zones and base prices, SEK excluding VAT.
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

    public static double BasePrice(int zone, double weightKg)
    {
        double billed = Math.Ceiling(weightKg * 2) / 2;
        return Start[zone] + PerKg[zone] * billed;
    }
}
