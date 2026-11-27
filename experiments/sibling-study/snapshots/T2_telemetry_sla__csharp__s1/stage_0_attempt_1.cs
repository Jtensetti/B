using System.Text.Json;
using System.Text.Json.Serialization;

namespace TelemetrySlaAuditor;

public sealed record RawSample(
    [property: JsonPropertyName("service")] string Service,
    [property: JsonPropertyName("ms")] long Ms,
    [property: JsonPropertyName("offset")] long Offset
);

public sealed record AuditInput(
    [property: JsonPropertyName("sla_s")] double SlaS,
    [property: JsonPropertyName("samples")] List<RawSample> Samples
);

public sealed record NormalizedSample(
    string Service,
    long Ms,
    long Offset
);

public sealed record AuditOutput(
    [property: JsonPropertyName("count")] long Count,
    [property: JsonPropertyName("breaches")] long Breaches,
    [property: JsonPropertyName("overage_ms")] long OverageMs,
    [property: JsonPropertyName("max_ms")] long MaxMs,
    [property: JsonPropertyName("mean_ms")] long MeanMs,
    [property: JsonPropertyName("bucket_zero")] long BucketZero
);

public static class Program
{
    public static void Main()
    {
        string rawJson = Console.In.ReadToEnd();
        AuditInput input = JsonSerializer.Deserialize<AuditInput>(rawJson)
            ?? throw new InvalidOperationException("Failed to deserialize input JSON.");

        AuditOutput result = Audit(input);
        Console.WriteLine(JsonSerializer.Serialize(result));
    }

    private static string NormalizeService(string service) =>
        service.Trim().ToLowerInvariant();

    private static long RemEuclid(long value, long modulus)
    {
        long remainder = value % modulus;
        return remainder < 0 ? remainder + Math.Abs(modulus) : remainder;
    }

    private static long RoundHalfToEven(double value) =>
        (long)Math.Round(value, MidpointRounding.ToEven);

    private static AuditOutput Audit(AuditInput input)
    {
        double slaMs = input.SlaS * 1000.0;
        long slaMsInt = RoundHalfToEven(slaMs);

        List<NormalizedSample> samples = input.Samples
            .Select(s => new NormalizedSample(NormalizeService(s.Service), s.Ms, s.Offset))
            .ToList();

        long count = samples.Count;
        if (count == 0)
        {
            return new AuditOutput(
                Count: 0,
                Breaches: 0,
                OverageMs: 0,
                MaxMs: 0,
                MeanMs: 0,
                BucketZero: 0
            );
        }

        long breaches = 0;
        long overageMs = 0;
        long maxMs = samples[0].Ms;
        long totalMs = 0;
        long bucketZero = 0;

        foreach (NormalizedSample sample in samples)
        {
            totalMs += sample.Ms;
            if (sample.Ms > maxMs)
            {
                maxMs = sample.Ms;
            }

            if ((double)sample.Ms > slaMs)
            {
                breaches++;
                overageMs += sample.Ms - slaMsInt;
            }

            if (RemEuclid(sample.Offset, 4) == 0)
            {
                bucketZero++;
            }
        }

        long meanMs = RoundHalfToEven((double)totalMs / count);

        return new AuditOutput(
            Count: count,
            Breaches: breaches,
            OverageMs: overageMs,
            MaxMs: maxMs,
            MeanMs: meanMs,
            BucketZero: bucketZero
        );
    }
}
