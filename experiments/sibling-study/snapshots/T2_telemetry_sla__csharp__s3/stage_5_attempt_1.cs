using System.Text;
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
    [property: JsonPropertyName("spike_steps")] int SpikeSteps,
    [property: JsonPropertyName("invalid_labels")] int InvalidLabels,
    [property: JsonPropertyName("exempt")] int Exempt,
    [property: JsonPropertyName("regressed")] int Regressed,
    [property: JsonPropertyName("status")] string Status);

public static class Program
{
    private const double MillisecondsPerSecond = 1000.0;
    private const long BucketModulus = 4;
    private const long SpikeThresholdMs = 100;
    private const long RegressionThresholdMs = 300;
    private const int MinServiceCodePoints = 2;
    private const int MaxServiceCodePoints = 12;
    private const string MaintenanceServiceName = "healthcheck";

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
                SpikeSteps: 0,
                InvalidLabels: 0,
                Exempt: 0,
                Regressed: 0,
                Status: "green");
        }

        int breaches = 0;
        long overageMs = 0;
        long maxMs = normalized[0].Ms;
        long earlierMinMs = normalized[0].Ms;
        long validSumMs = 0;
        int validCount = 0;
        int invalidLabels = 0;
        int bucketZero = 0;
        int critical = 0;
        int warnOrWorse = 0;
        int consecutiveBreaches = 0;
        int spikeSteps = 0;
        int exempt = 0;
        int regressed = 0;

        NormalizedSample? previous = null;
        bool previousBreached = false;

        foreach (NormalizedSample sample in normalized)
        {
            bool isBucketZero = RemEuclid(sample.Offset, BucketModulus) == 0;
            bool rawBreach = IsRawBreach(sample.Ms, slaMs);
            bool isExempt = IsMaintenanceExempt(sample.Service, isBucketZero);
            bool breached = rawBreach && !isExempt;

            if (rawBreach && isExempt)
            {
                exempt++;
            }

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

                if (earlierMinMs + RegressionThresholdMs < sample.Ms)
                {
                    regressed++;
                }
            }

            if (sample.Ms < earlierMinMs)
            {
                earlierMinMs = sample.Ms;
            }

            if (sample.Ms > maxMs)
            {
                maxMs = sample.Ms;
            }

            if (IsValidServiceLabel(sample.Service))
            {
                validSumMs += sample.Ms;
                validCount++;
            }
            else
            {
                invalidLabels++;
            }

            if (isBucketZero)
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

        long meanMs = validCount == 0 ? 0 : RoundHalfToEven((double)validSumMs / validCount);
        string status = DetermineStatus(consecutiveBreaches, critical, breaches, invalidLabels);

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
            SpikeSteps: spikeSteps,
            InvalidLabels: invalidLabels,
            Exempt: exempt,
            Regressed: regressed,
            Status: status);
    }

    private static string DetermineStatus(
        int consecutiveBreaches,
        int critical,
        int breaches,
        int invalidLabels)
    {
        if (consecutiveBreaches >= 2 || critical > 0)
        {
            return "red";
        }

        if (breaches > 0 || invalidLabels > 0)
        {
            return "yellow";
        }

        return "green";
    }

    private static bool IsRawBreach(long ms, double slaMs) => (double)ms > slaMs;

    private static bool IsMaintenanceExempt(string normalizedService, bool isBucketZero) =>
        isBucketZero && string.Equals(normalizedService, MaintenanceServiceName, StringComparison.Ordinal);

    private static bool IsValidServiceLabel(string normalizedService)
    {
        int codePoints = CountCodePoints(normalizedService);
        return codePoints >= MinServiceCodePoints && codePoints <= MaxServiceCodePoints;
    }

    private static int CountCodePoints(string text)
    {
        int count = 0;
        foreach (Rune _ in text.EnumerateRunes())
        {
            count++;
        }

        return count;
    }

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
