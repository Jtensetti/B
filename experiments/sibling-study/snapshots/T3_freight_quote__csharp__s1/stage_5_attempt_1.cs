using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace FreightQuote;

public sealed record QuoteRequest
{
    [JsonPropertyName("eur_to_sek")]
    public double EurToSek { get; init; }

    [JsonPropertyName("max_sek")]
    public long MaxSek { get; init; }

    [JsonPropertyName("legs")]
    public List<LegInput>? Legs { get; init; }
}

public sealed record LegInput
{
    [JsonPropertyName("route")]
    public string Route { get; init; } = "";

    [JsonPropertyName("dx_km")]
    public double DxKm { get; init; }

    [JsonPropertyName("dy_km")]
    public double DyKm { get; init; }

    [JsonPropertyName("weight_g")]
    public double WeightG { get; init; }

    [JsonPropertyName("zone")]
    public string Zone { get; init; } = "";
}

public sealed record QuoteResponse
{
    [JsonPropertyName("legs")]
    public int Legs { get; init; }

    [JsonPropertyName("valid_legs")]
    public int ValidLegs { get; init; }

    [JsonPropertyName("total_m")]
    public long TotalM { get; init; }

    [JsonPropertyName("total_eur_cents")]
    public long TotalEurCents { get; init; }

    [JsonPropertyName("total_sek")]
    public long TotalSek { get; init; }

    [JsonPropertyName("heavy_legs")]
    public int HeavyLegs { get; init; }

    [JsonPropertyName("customs_legs")]
    public int CustomsLegs { get; init; }

    [JsonPropertyName("long_haul_pairs")]
    public int LongHaulPairs { get; init; }

    [JsonPropertyName("vip_exempt")]
    public int VipExempt { get; init; }

    [JsonPropertyName("within_cap")]
    public bool WithinCap { get; init; }

    [JsonPropertyName("max_leg_eur_cents")]
    public long MaxLegEurCents { get; init; }
}

public static class Program
{
    private static readonly Regex DepotRegex = new(
        @"\A[a-z]{3}-[0-9]{2}\z",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private static readonly HashSet<string> ValidZones = new(StringComparer.Ordinal)
    {
        "SE",
        "EU",
        "NON-EU"
    };

    public static void Main()
    {
        string input = Console.In.ReadToEnd();
        QuoteRequest request = JsonSerializer.Deserialize<QuoteRequest>(input)
            ?? throw new InvalidOperationException("Failed to deserialize input JSON.");

        QuoteResponse response = ComputeQuote(request);
        Console.WriteLine(JsonSerializer.Serialize(response));
    }

    private static QuoteResponse ComputeQuote(QuoteRequest request)
    {
        List<LegInput> legs = request.Legs ?? [];
        int validLegs = 0;
        int heavyLegs = 0;
        int customsLegs = 0;
        int longHaulPairs = 0;
        int vipExempt = 0;
        bool prevLongHaul = false;
        double totalKm = 0.0;
        double totalEur = 0.0;
        long maxLegEurCents = 0;

        foreach (LegInput leg in legs)
        {
            string normRoute = NormalizePosixPath(leg.Route ?? "");
            string depot = PosixBasename(normRoute);
            string zone = (leg.Zone ?? "").Trim().ToUpperInvariant();

            if (!DepotRegex.IsMatch(depot) || !ValidZones.Contains(zone))
            {
                continue;
            }

            validLegs++;
            double km = Math.Sqrt(leg.DxKm * leg.DxKm + leg.DyKm * leg.DyKm);
            double kg = leg.WeightG / 1000.0;
            double baseEur = 5.0 + 0.5 * km + 2.0 * kg;
            double distanceMultiplier = km switch
            {
                <= 50.0 => 1.0,
                <= 200.0 => 1.15,
                _ => 1.35
            };
            double legEur = baseEur * distanceMultiplier;

            if (kg >= 10.0)
            {
                heavyLegs++;
                if (depot == "sto-01" && zone == "SE")
                {
                    vipExempt++;
                }
                else
                {
                    legEur += 12.0;
                }
            }

            if (zone == "SE")
            {
                legEur *= 0.9;
            }
            else if (zone == "NON-EU")
            {
                customsLegs++;
                legEur += 15.0;
            }

            bool isLongHaul = km > 100.0;
            if (prevLongHaul && isLongHaul)
            {
                longHaulPairs++;
            }
            prevLongHaul = isLongHaul;

            long legEurCents = RoundToEven(legEur * 100.0);
            if (validLegs == 1 || legEurCents > maxLegEurCents)
            {
                maxLegEurCents = legEurCents;
            }

            totalKm += km;
            totalEur += legEur;
        }

        totalEur += 25.0 * longHaulPairs;
        long totalSek = RoundToEven(totalEur * request.EurToSek);

        return new QuoteResponse
        {
            Legs = legs.Count,
            ValidLegs = validLegs,
            TotalM = RoundToEven(totalKm * 1000.0),
            TotalEurCents = RoundToEven(totalEur * 100.0),
            TotalSek = totalSek,
            HeavyLegs = heavyLegs,
            CustomsLegs = customsLegs,
            LongHaulPairs = longHaulPairs,
            VipExempt = vipExempt,
            WithinCap = totalSek <= request.MaxSek,
            MaxLegEurCents = maxLegEurCents
        };
    }

    private static long RoundToEven(double value) =>
        (long)Math.Round(value, MidpointRounding.ToEven);

    private static string NormalizePosixPath(string path)
    {
        if (string.IsNullOrEmpty(path))
        {
            return ".";
        }

        bool isAbsolute = path[0] == '/';
        List<string> segments = [];

        foreach (string part in path.Split('/'))
        {
            if (part.Length == 0 || part == ".")
            {
                continue;
            }

            if (part == "..")
            {
                if (segments.Count > 0 && segments[^1] != "..")
                {
                    segments.RemoveAt(segments.Count - 1);
                }
                else if (!isAbsolute)
                {
                    segments.Add("..");
                }
            }
            else
            {
                segments.Add(part);
            }
        }

        if (segments.Count == 0)
        {
            return isAbsolute ? "/" : ".";
        }

        string joined = string.Join('/', segments);
        return isAbsolute ? "/" + joined : joined;
    }

    private static string PosixBasename(string path)
    {
        int lastSlash = path.LastIndexOf('/');
        return lastSlash < 0 ? path : path[(lastSlash + 1)..];
    }
}
