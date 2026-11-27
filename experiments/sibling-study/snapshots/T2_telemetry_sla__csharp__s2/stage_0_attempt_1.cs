using System.Text.Json;
using System.Text.Json.Serialization;

namespace TelemetrySlaAuditor;

public sealed record InputPayload(
    [property: JsonPropertyName("sla_s")] double SlaSeconds,
    [property: JsonPropertyName("samples")] List<SampleInput> Samples
);

public sealed record SampleInput(
    [property: JsonPropertyName("service")] string Service,
    [property: JsonPropertyName("ms")] long LatencyMs,
    [property: JsonPropertyName("offset")] long Offset
);

public sealed record NormalizedSample(
    string Service,
    long LatencyMs,
    long Offset
);

public sealed record AuditOutput(
    [property: JsonPropertyName("count")] int Count,
    [property: JsonPropertyName("breaches")] int Breaches,
    [property: JsonPropertyName("overage_ms")] long OverageMs,
    [property: JsonPropertyName("max_ms")] long MaxMs,
    [property: JsonPropertyName("mean_ms")] long MeanMs,
    [property: JsonPropertyName("bucket_zero")] int BucketZero
);

public static class Program
{
    private const long BucketDivisor = 4;

    public static void Main()
    {
        string rawInput = Console.In.ReadToEnd();
        InputPayload payload = JsonSerializer.Deserialize<InputPayload>(rawInput)
            ?? throw new InvalidOperationException("Failed to deserialize input JSON.");

        AuditOutput output = Audit(payload);
        Console.WriteLine(JsonSerializer.Serialize(output));
    }

    public static AuditOutput Audit(InputPayload payload)
    {
        double slaMs = payload.SlaSeconds * 1000.0;
        long slaMsInt = RoundHalfToEven(slaMs);

        List<NormalizedSample> samples = payload.Samples
            .Select(s => new NormalizedSample(NormalizeService(s.Service), s.LatencyMs, s.Offset))
            .ToList();

        int count = samples.Count;
        int breaches = 0;
        long overageMs = 0;
        long sumMs = 0;
        long maxMs = count > 0 ? long.MinValue : 0;
        int bucketZero = 0;

        foreach (NormalizedSample sample in samples)
        {
            sumMs += sample.LatencyMs;
            if (sample.LatencyMs > maxMs)
            {
                maxMs = sample.LatencyMs;
            }

            if ((double)sample.LatencyMs > slaMs)
            {
                breaches++;
                overageMs += sample.LatencyMs - slaMsInt;
            }

            if (RemEuclid(sample.Offset, BucketDivisor) == 0)
            {
                bucketZero++;
            }
        }

        long meanMs = count > 0
            ? RoundHalfToEven((double)sumMs / count)
            : 0;

        return new AuditOutput(
            Count: count,
            Breaches: breaches,
            OverageMs: overageMs,
            MaxMs: maxMs,
            MeanMs: meanMs,
            BucketZero: bucketZero
        );
    }

    private static string NormalizeService(string service) =>
        service.Trim().ToLowerInvariant();

    private static long RoundHalfToEven(double value) =>
        (long)Math.Round(value, MidpointRounding.ToEven);

    private static long RemEuclid(long dividend, long divisor)
    {
        long remainder = dividend % divisor;
        return remainder < 0 ? remainder + divisor : remainder;
    }
}
