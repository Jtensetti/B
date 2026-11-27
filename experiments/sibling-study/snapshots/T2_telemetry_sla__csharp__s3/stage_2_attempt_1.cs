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

public enum LatencySeverity
{
    Ok,
    Warn,
    Slow,
    Critical
}

public sealed record TelemetrySummary(
    [property: JsonPropertyName("count")] int Count,
    [property: JsonPropertyName("breaches")] int Breaches,
    [property: JsonPropertyName("overage_ms")] long OverageMs,
    [property: JsonPropertyName("max_ms")] long MaxMs,
    [property: JsonPropertyName("mean_ms")] long MeanMs,
    [property: JsonPropertyName("bucket_zero")] int BucketZero,
    [property: JsonPropertyName("critical")] int Critical,
    [property: JsonPropertyName("warn_or_worse")] int WarnOrWorse,
    [property: JsonPropertyName("consecutive_breaches")] int ConsecutiveBreaches,
    [property: JsonPropertyName("spike_steps")] int SpikeSteps);

public static class Program
{
    private const double MillisecondsPerSecond = 1000.0;
    private const long BucketModulus = 4;
    private const long SpikeThresholdMs = 100;

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
                BucketZero: 0,
                Critical: 0,
                WarnOrWorse: 0,
                ConsecutiveBreaches: 0,
                SpikeSteps: 0);
        }

        int breaches = 0;
        long overageMs = 0;
        long maxMs = normalized[0].Ms;
        long sumMs = 0;
        int bucketZero = 0;
        int critical = 0;
        int warnOrWorse = 0;
        int consecutiveBreaches = 0;
        int spikeSteps = 0;

        NormalizedSample? previous = null;
        bool previousBreached = false;

        foreach (NormalizedSample sample in normalized)
        {
            bool breached = IsBreach(sample.Ms, slaMs);
            if (breached)
            {
                breaches++;
                overageMs += sample.Ms - slaMsInt;
            }

            if (previous is not null)
            {
                if (previousBreached && breached)
                {
                    consecutiveBreaches++;
                }

                if (sample.Ms > previous.Ms + SpikeThresholdMs)
                {
                    spikeSteps++;
                }
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

            LatencySeverity severity = ClassifySeverity(sample.Ms);
            if (severity == LatencySeverity.Critical)
            {
                critical++;
            }

            if (severity != LatencySeverity.Ok)
            {
                warnOrWorse++;
            }

            previous = sample;
            previousBreached = breached;
        }

        long meanMs = RoundHalfToEven((double)sumMs / count);

        return new TelemetrySummary(
            Count: count,
            Breaches: breaches,
            OverageMs: overageMs,
            MaxMs: maxMs,
            MeanMs: meanMs,
            BucketZero: bucketZero,
            Critical: critical,
            WarnOrWorse: warnOrWorse,
            ConsecutiveBreaches: consecutiveBreaches,
            SpikeSteps: spikeSteps);
    }

    private static bool IsBreach(long ms, double slaMs) => (double)ms > slaMs;

    private static LatencySeverity ClassifySeverity(long ms) => ms switch
    {
        < 200 => LatencySeverity.Ok,
        <= 500 => LatencySeverity.Warn,
        <= 1000 => LatencySeverity.Slow,
        _ => LatencySeverity.Critical
    };

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
