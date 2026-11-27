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

public enum LatencySeverity
{
    Ok,
    Warn,
    Slow,
    Critical
}

public sealed record AuditOutput(
    [property: JsonPropertyName("count")] int Count,
    [property: JsonPropertyName("breaches")] int Breaches,
    [property: JsonPropertyName("overage_ms")] long OverageMs,
    [property: JsonPropertyName("max_ms")] long MaxMs,
    [property: JsonPropertyName("mean_ms")] long MeanMs,
    [property: JsonPropertyName("bucket_zero")] int BucketZero,
    [property: JsonPropertyName("critical")] int Critical,
    [property: JsonPropertyName("warn_or_worse")] int WarnOrWorse,
    [property: JsonPropertyName("consecutive_breaches")] int ConsecutiveBreaches,
    [property: JsonPropertyName("spike_steps")] int SpikeSteps
);

public static class Program
{
    private const long BucketDivisor = 4;
    private const long SpikeThresholdMs = 100;

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
        int critical = 0;
        int warnOrWorse = 0;
        int consecutiveBreaches = 0;
        int spikeSteps = 0;

        NormalizedSample? previousSample = null;
        bool previousBreached = false;

        foreach (NormalizedSample sample in samples)
        {
            sumMs += sample.LatencyMs;
            if (sample.LatencyMs > maxMs)
            {
                maxMs = sample.LatencyMs;
            }

            bool isBreach = IsBreach(sample.LatencyMs, slaMs);
            if (isBreach)
            {
                breaches++;
                overageMs += sample.LatencyMs - slaMsInt;
            }

            if (RemEuclid(sample.Offset, BucketDivisor) == 0)
            {
                bucketZero++;
            }

            LatencySeverity severity = ClassifySeverity(sample.LatencyMs);
            if (severity == LatencySeverity.Critical)
            {
                critical++;
            }

            if (severity != LatencySeverity.Ok)
            {
                warnOrWorse++;
            }

            if (previousSample is not null)
            {
                if (previousBreached && isBreach)
                {
                    consecutiveBreaches++;
                }

                if (sample.LatencyMs > previousSample.LatencyMs + SpikeThresholdMs)
                {
                    spikeSteps++;
                }
            }

            previousSample = sample;
            previousBreached = isBreach;
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
            BucketZero: bucketZero,
            Critical: critical,
            WarnOrWorse: warnOrWorse,
            ConsecutiveBreaches: consecutiveBreaches,
            SpikeSteps: spikeSteps
        );
    }

    private static bool IsBreach(long latencyMs, double slaMs) =>
        (double)latencyMs > slaMs;

    private static LatencySeverity ClassifySeverity(long latencyMs) => latencyMs switch
    {
        < 200 => LatencySeverity.Ok,
        <= 500 => LatencySeverity.Warn,
        <= 1000 => LatencySeverity.Slow,
        _ => LatencySeverity.Critical
    };

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
