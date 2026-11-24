using System.Text.Json;
using System.Text.Json.Nodes;

// Ported from libs/tariff (Go), libs/geo (Rust), libs/calendar (Python),
// fastest-levenshtein (JS). VAT comes from libs/Tax via Compile Include.

static class Program
{
    static void Main()
    {
        var input = Console.In.ReadToEnd();
        using var doc = JsonDocument.Parse(input);
        var root = doc.RootElement;

        var depot = root.GetProperty("depot");
        double depLat = depot.GetProperty("lat").GetDouble();
        double depLon = depot.GetProperty("lon").GetDouble();

        var catalog = new SortedDictionary<string, double>(StringComparer.Ordinal);
        foreach (var p in root.GetProperty("catalog").EnumerateObject())
            catalog[p.Name] = p.Value.GetDouble();

        double eurRate = 0.0;
        if (root.TryGetProperty("rates", out var rates) && rates.TryGetProperty("EUR", out var eur))
            eurRate = eur.GetDouble();

        var quotes = new SortedDictionary<string, JsonObject>(StringComparer.Ordinal);
        var unknown = new List<string>();

        foreach (var o in root.GetProperty("orders").EnumerateArray())
        {
            string id = o.GetProperty("id").GetString()!;
            string product = o.GetProperty("product").GetString()!;
            string country = o.GetProperty("country").GetString()!;
            double lat = o.GetProperty("lat").GetDouble();
            double lon = o.GetProperty("lon").GetDouble();
            string date = o.GetProperty("date").GetString()!;
            bool business = o.GetProperty("business").GetBoolean();
            double qty = o.TryGetProperty("qty", out var qe) && qe.ValueKind == JsonValueKind.Number
                ? qe.GetDouble() : 1.0;
            bool express = o.TryGetProperty("express", out var ee) && ee.ValueKind == JsonValueKind.True;

            if (!TryQuote(catalog, depLat, depLon, product, country, lat, lon, date, business, qty, express, out var q))
            {
                unknown.Add(id);
                continue;
            }
            bool sweden = country.Trim().ToUpperInvariant() == "SE";
            double price = q.price;
            string currency = "SEK";
            if (!sweden)
            {
                price = Math.Round(q.price / eurRate, 2, MidpointRounding.AwayFromZero);
                currency = "EUR";
            }
            quotes[id] = new JsonObject { ["price"] = price, ["delivery"] = q.delivery, ["currency"] = currency };
        }

        unknown.Sort(StringComparer.Ordinal);
        var quoteObj = new JsonObject();
        foreach (var kv in quotes) quoteObj[kv.Key] = kv.Value;
        var outObj = new JsonObject
        {
            ["quotes"] = quoteObj,
            ["unknown"] = new JsonArray(unknown.Select(u => (JsonNode)JsonValue.Create(u)!).ToArray()),
        };
        Console.Out.WriteLine(outObj.ToJsonString());
    }

    static bool TryQuote(SortedDictionary<string, double> catalog, double depLat, double depLon,
        string product, string country, double lat, double lon, string date, bool business, double qty, bool express,
        out (double price, string delivery) result)
    {
        result = default;

        // Product: nearest catalog name within distance 2, ties to alphabetically first.
        string? best = null;
        int bestDist = int.MaxValue;
        foreach (var name in catalog.Keys) // sorted ordinal, so first minimum wins ties
        {
            int d = Levenshtein(product, name);
            if (d < bestDist) { bestDist = d; best = name; }
        }
        if (best is null || bestDist > 2) return false;
        double weight = catalog[best] * qty;

        // Tariff zone: unknown country is unknown order.
        string cc = country.Trim().ToUpperInvariant();
        if (!Zone.TryGetValue(cc, out int zone)) return false;

        double billed = Math.Ceiling(weight * 2) / 2;
        double basePrice = Start[zone] + PerKg[zone] * billed;
        // Free freight: business parcels of 50 kg or more have no base price.
        if (business && weight >= 50.0) basePrice = 0.0;
        if (express) basePrice *= 1.5;

        double road = DistanceKm(depLat, depLon, lat, lon) * 1.25;
        double extra = Math.Min(400.0, Math.Max(0.0, road - 300.0) * 0.80);
        double net = basePrice + extra;

        double vat = Tax.Vat.ReverseCharge(cc, business) ? 0.0 : Tax.Vat.Rate(cc);
        double price = Math.Round(net * (1 + vat), 2, MidpointRounding.AwayFromZero);

        string delivery = express && IsWorkday(DateOnly.ParseExact(date, "yyyy-MM-dd"))
            ? date
            : NextWorkday(date);
        result = (price, delivery);
        return true;
    }

    // ---- tariff (libs/tariff/tariff.go) ----
    static readonly Dictionary<string, int> Zone = new()
    {
        ["SE"] = 1, ["NO"] = 2, ["DK"] = 2, ["FI"] = 2, ["DE"] = 3, ["NL"] = 3, ["PL"] = 3,
        ["FR"] = 4, ["ES"] = 4, ["IT"] = 4,
    };
    static readonly Dictionary<int, double> Start = new() { [1] = 49, [2] = 79, [3] = 99, [4] = 129 };
    static readonly Dictionary<int, double> PerKg = new() { [1] = 6.5, [2] = 9.0, [3] = 11.0, [4] = 14.5 };

    // ---- geo (libs/geo/src/lib.rs) ----
    const double EarthRadiusKm = 6371.0;

    static double DistanceKm(double lat1, double lon1, double lat2, double lon2)
    {
        double p1 = DegToRad(lat1), p2 = DegToRad(lat2);
        double dp = DegToRad(lat2 - lat1);
        double dl = DegToRad(lon2 - lon1);
        double a = Math.Pow(Math.Sin(dp / 2.0), 2) + Math.Cos(p1) * Math.Cos(p2) * Math.Pow(Math.Sin(dl / 2.0), 2);
        return 2.0 * EarthRadiusKm * Math.Asin(Math.Sqrt(a));
    }

    static double DegToRad(double d) => d * Math.PI / 180.0;

    // ---- calendar (libs/calendar/workdays.py) ----
    static readonly HashSet<string> Holidays2026 = new()
    {
        "2026-01-01", "2026-01-06", "2026-04-03", "2026-04-06", "2026-05-01", "2026-05-14",
        "2026-06-06", "2026-06-19", "2026-12-24", "2026-12-25", "2026-12-26", "2026-12-31",
    };

    static bool IsWorkday(DateOnly d)
    {
        var dow = d.DayOfWeek;
        bool weekday = dow != DayOfWeek.Saturday && dow != DayOfWeek.Sunday;
        return weekday && !Holidays2026.Contains(d.ToString("yyyy-MM-dd"));
    }

    static string NextWorkday(string iso)
    {
        var d = DateOnly.ParseExact(iso, "yyyy-MM-dd").AddDays(1);
        while (!IsWorkday(d)) d = d.AddDays(1);
        return d.ToString("yyyy-MM-dd");
    }

    // ---- Levenshtein (fastest-levenshtein distance, unit costs) ----
    static int Levenshtein(string a, string b)
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
                cur[j] = Math.Min(Math.Min(prev[j] + 1, cur[j - 1] + 1), prev[j - 1] + cost);
            }
            (prev, cur) = (cur, prev);
        }
        return prev[b.Length];
    }
}
