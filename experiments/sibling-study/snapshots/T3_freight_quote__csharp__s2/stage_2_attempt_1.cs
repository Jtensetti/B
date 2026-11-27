using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace FreightQuote;

internal sealed class QuoteInput
{
    [JsonPropertyName("eur_to_sek")]
    public double EurToSek { get; init; }

    [JsonPropertyName("legs")]
    public List<LegInput> Legs { get; init; } = new();
}

internal sealed class LegInput
{
    [JsonPropertyName("route")]
    public string Route { get; init; } = string.Empty;

    [JsonPropertyName("dx_km")]
    public double DxKm { get; init; }

    [JsonPropertyName("dy_km")]
    public double DyKm { get; init; }

    [JsonPropertyName("weight_g")]
    public double WeightG { get; init; }

    [JsonPropertyName("zone")]
    public string Zone { get; init; } = string.Empty;
}

internal sealed class QuoteOutput
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
}

internal static class Program
{
    private static readonly Regex DepotPattern = new(
        @"\A[a-z]{3}-[0-9]{2}\z",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private static readonly HashSet<string> ValidZones = new(StringComparer.Ordinal)
    {
        "SE",
        "EU",
        "NON-EU"
    };

    private static void Main()
    {
        string rawInput = Console.In.ReadToEnd();
        QuoteInput input = JsonSerializer.Deserialize<QuoteInput>(rawInput)
            ?? throw new InvalidOperationException("Invalid JSON input.");

        QuoteOutput output = ComputeQuote(input);
        Console.WriteLine(JsonSerializer.Serialize(output));
    }

    private static QuoteOutput ComputeQuote(QuoteInput input)
    {
        int totalLegs = input.Legs.Count;
        int validLegs = 0;
        int heavyLegs = 0;
        int customsLegs = 0;
        double totalKm = 0.0;
        double totalEur = 0.0;

        foreach (LegInput leg in input.Legs)
        {
            string normalizedRoute = NormalizePosixPath(leg.Route);
            string depot = PosixBasename(normalizedRoute);
            string zone = (leg.Zone ?? string.Empty).Trim().ToUpperInvariant();

            if (!DepotPattern.IsMatch(depot) || !ValidZones.Contains(zone))
            {
                continue;
            }

            double km = Math.Sqrt(leg.DxKm * leg.DxKm + leg.DyKm * leg.DyKm);
            double kg = leg.WeightG / 1000.0;
            double baseEur = 5.0 + 0.5 * km + 2.0 * kg;
            double distanceMultiplier = km <= 50.0 ? 1.0 : km <= 200.0 ? 1.15 : 1.35;
            double legEur = baseEur * distanceMultiplier;

            if (kg >= 10.0)
            {
                legEur += 12.0;
                heavyLegs++;
            }

            if (zone == "SE")
            {
                legEur *= 0.9;
            }
            else if (zone == "NON-EU")
            {
                legEur += 15.0;
                customsLegs++;
            }

            validLegs++;
            totalKm += km;
            totalEur += legEur;
        }

        return new QuoteOutput
        {
            Legs = totalLegs,
            ValidLegs = validLegs,
            TotalM = RoundToEven(totalKm * 1000.0),
            TotalEurCents = RoundToEven(totalEur * 100.0),
            TotalSek = RoundToEven(totalEur * input.EurToSek),
            HeavyLegs = heavyLegs,
            CustomsLegs = customsLegs
        };
    }

    private static string NormalizePosixPath(string? path)
    {
        if (string.IsNullOrEmpty(path))
        {
            return ".";
        }

        bool isAbsolute = path.StartsWith('/');
        var segments = new List<string>();

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

    private static string PosixBasename(string normalizedPath)
    {
        if (string.IsNullOrEmpty(normalizedPath) || normalizedPath == "/")
        {
            return string.Empty;
        }

        int lastSlash = normalizedPath.LastIndexOf('/');
        return lastSlash < 0 ? normalizedPath : normalizedPath[(lastSlash + 1)..];
    }

    private static long RoundToEven(double value)
    {
        return (long)Math.Round(value, MidpointRounding.ToEven);
    }
}
