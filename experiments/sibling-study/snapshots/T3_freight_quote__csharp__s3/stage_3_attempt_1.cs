using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace FreightQuote;

public sealed record LegInput(
    [property: JsonPropertyName("route")] string Route,
    [property: JsonPropertyName("dx_km")] double DxKm,
    [property: JsonPropertyName("dy_km")] double DyKm,
    [property: JsonPropertyName("weight_g")] double WeightG,
    [property: JsonPropertyName("zone")] string Zone
);

public sealed record QuoteRequest(
    [property: JsonPropertyName("eur_to_sek")] double EurToSek,
    [property: JsonPropertyName("legs")] List<LegInput> Legs
);

public sealed record QuoteResponse(
    [property: JsonPropertyName("legs")] int Legs,
    [property: JsonPropertyName("valid_legs")] int ValidLegs,
    [property: JsonPropertyName("total_m")] long TotalM,
    [property: JsonPropertyName("total_eur_cents")] long TotalEurCents,
    [property: JsonPropertyName("total_sek")] long TotalSek,
    [property: JsonPropertyName("heavy_legs")] int HeavyLegs,
    [property: JsonPropertyName("customs_legs")] int CustomsLegs,
    [property: JsonPropertyName("long_haul_pairs")] int LongHaulPairs
);

public static class Program
{
    private static readonly Regex DepotRegex = new(@"\A[a-z]{3}-[0-9]{2}\z", RegexOptions.Compiled);
    private static readonly HashSet<string> ValidZones = new(StringComparer.Ordinal) { "SE", "EU", "NON-EU" };

    public static void Main()
    {
        string input = Console.In.ReadToEnd();
        QuoteRequest request = JsonSerializer.Deserialize<QuoteRequest>(input)
            ?? throw new InvalidOperationException("Failed to deserialize quote request.");

        QuoteResponse response = EvaluateQuote(request);
        Console.WriteLine(JsonSerializer.Serialize(response));
    }

    private static QuoteResponse EvaluateQuote(QuoteRequest request)
    {
        int totalLegs = request.Legs.Count;
        int validLegs = 0;
        int heavyLegs = 0;
        int customsLegs = 0;
        int longHaulPairs = 0;
        bool prevWasLongHaul = false;
        double totalKm = 0.0;
        double totalEur = 0.0;

        foreach (LegInput leg in request.Legs)
        {
            string normalizedRoute = NormalizePosixPath(leg.Route);
            string depot = PosixBasename(normalizedRoute);
            string zone = leg.Zone.Trim().ToUpperInvariant();

            if (!DepotRegex.IsMatch(depot) || !ValidZones.Contains(zone))
            {
                continue;
            }

            validLegs++;
            double km = Math.Sqrt(leg.DxKm * leg.DxKm + leg.DyKm * leg.DyKm);
            double kg = leg.WeightG / 1000.0;
            double baseEur = 5.0 + 0.5 * km + 2.0 * kg;
            double distanceMultiplier = DistanceMultiplier(km);
            double legEur = baseEur * distanceMultiplier;

            if (kg >= 10.0)
            {
                heavyLegs++;
                legEur += 12.0;
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
            if (prevWasLongHaul && isLongHaul)
            {
                longHaulPairs++;
            }
            prevWasLongHaul = isLongHaul;

            totalKm += km;
            totalEur += legEur;
        }

        totalEur += 25.0 * longHaulPairs;

        long totalM = RoundToEven(totalKm * 1000.0);
        long totalEurCents = RoundToEven(totalEur * 100.0);
        long totalSek = RoundToEven(totalEur * request.EurToSek);

        return new QuoteResponse(
            Legs: totalLegs,
            ValidLegs: validLegs,
            TotalM: totalM,
            TotalEurCents: totalEurCents,
            TotalSek: totalSek,
            HeavyLegs: heavyLegs,
            CustomsLegs: customsLegs,
            LongHaulPairs: longHaulPairs
        );
    }

    private static double DistanceMultiplier(double km) =>
        km <= 50.0 ? 1.0 :
        km <= 200.0 ? 1.15 :
        1.35;

    private static long RoundToEven(double value) =>
        (long)Math.Round(value, MidpointRounding.ToEven);

    private static string NormalizePosixPath(string path)
    {
        if (string.IsNullOrEmpty(path))
        {
            return ".";
        }

        bool isAbsolute = path.StartsWith('/');
        bool preserveDoubleSlash = path.StartsWith("//", StringComparison.Ordinal)
            && !path.StartsWith("///", StringComparison.Ordinal);

        List<string> stack = new();
        foreach (string part in path.Split('/'))
        {
            if (part.Length == 0 || part == ".")
            {
                continue;
            }

            if (part == "..")
            {
                if (stack.Count > 0 && stack[^1] != "..")
                {
                    stack.RemoveAt(stack.Count - 1);
                }
                else if (!isAbsolute)
                {
                    stack.Add("..");
                }
            }
            else
            {
                stack.Add(part);
            }
        }

        if (isAbsolute)
        {
            string prefix = preserveDoubleSlash ? "//" : "/";
            return prefix + string.Join('/', stack);
        }

        return stack.Count == 0 ? "." : string.Join('/', stack);
    }

    private static string PosixBasename(string normalizedPath)
    {
        int idx = normalizedPath.LastIndexOf('/');
        return idx >= 0 ? normalizedPath[(idx + 1)..] : normalizedPath;
    }
}
