using System.Text.Json;
using System.Text.Json.Serialization;

namespace TelemetrySlaAuditor;

public sealed record TelemetryInput(
    [property: JsonPropertyName("sla_s")] double SlaSeconds,
    [property: JsonPropertyName("samples")] IReadOnlyList<TelemetrySample> Samples);

public sealed record TelemetrySample(
    [property: JsonPropertyName("service")] string Service,
    [property: JsonPropertyName("ms")] long Ms,
    [property: JsonPropertyName("offset")] long Offset);

public sealed record NormalizedSample(
    string Service,
    long Ms,
    long Offset);

public sealed record TelemetrySummary(
    [property: JsonPropertyName("count")] int Count,
    [property: JsonPropertyName("breaches")] int Breaches,
    [property: JsonPropertyName("overage_ms")] long OverageMs,
    [property: JsonPropertyName("max_ms")] long MaxMs,
    [property: JsonPropertyName("mean_ms")] long MeanMs,
    [property: JsonPropertyName("bucket_zero")] int BucketZero);

public static class Program
{
    private const double MillisecondsPerSecond = 1000.0;
    private const long BucketModulus = 4;

    public static void Main()
    {
        string rawInput = Console.In.ReadToEnd();
        TelemetryInput input = JsonSerializer.Deserialize<TelemetryInput>(rawInput)
            ?? throw new InvalidDataException("Input JSON could not be deserialized.");

        TelemetrySummary summary = Evaluate(input);
        Console.WriteLine(JsonSerializer.Serialize(summary));
    }

    private static TelemetrySummary Evaluate(TelemetryInput input)
    {
        double slaMs = input.SlaSeconds * MillisecondsPerSecond;
        long slaMsInt = RoundHalfToEven(slaMs);

        List<NormalizedSample> normalized = NormalizeSamples(input.Samples);
        int count = normalized.Count;
        if (count == 0)
        {
            return new TelemetrySummary(
                Count: 0,
                Breaches: 0,
                OverageMs: 0,
                MaxMs: 0,
                MeanMs: 0,
                BucketZero: 0);
        }

        int breaches = 0;
        long overageMs = 0;
        long maxMs = normalized[0].Ms;
        long sumMs = 0;
        int bucketZero = 0;

        foreach (NormalizedSample sample in normalized)
        {
            if ((double)sample.Ms > slaMs)
            {
                breaches++;
                overageMs += sample.Ms - slaMsInt;
            }

            if (sample.Ms > maxMs)
            {
                maxMs = sample.Ms;
            }

            sumMs += sample.Ms;

            if (RemEuclid(sample.Offset, BucketModulus) == 0)
            {
                bucketZero++;
            }
        }

        long meanMs = RoundHalfToEven((double)sumMs / count);

        return new TelemetrySummary(
            Count: count,
            Breaches: breaches,
            OverageMs: overageMs,
            MaxMs: maxMs,
            MeanMs: meanMs,
            BucketZero: bucketZero);
    }

    private static List<NormalizedSample> NormalizeSamples(IReadOnlyList<TelemetrySample> samples)
    {
        var result = new List<NormalizedSample>(samples.Count);
        foreach (TelemetrySample sample in samples)
        {
            string normalizedService = sample.Service.Trim().ToLowerInvariant();
            result.Add(new NormalizedSample(normalizedService, sample.Ms, sample.Offset));
        }

        return result;
    }

    private static long RoundHalfToEven(double value) =>
        (long)Math.Round(value, MidpointRounding.ToEven);

    private static long RemEuclid(long value, long divisor)
    {
        long remainder = value % divisor;
        return remainder < 0 ? remainder + Math.Abs(divisor) : remainder;
    }
}
