using System.Text;
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
    long Offset,
    bool HasValidLabel
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
    [property: JsonPropertyName("spike_steps")] int SpikeSteps,
    [property: JsonPropertyName("invalid_labels")] int InvalidLabels,
    [property: JsonPropertyName("exempt")] int Exempt,
    [property: JsonPropertyName("regressed")] int Regressed,
    [property: JsonPropertyName("status")] string Status
);

public static class Program
{
    private const long BucketDivisor = 4;
    private const long SpikeThresholdMs = 100;
    private const long RegressionThresholdMs = 300;
    private const int MinServiceCodePoints = 2;
    private const int MaxServiceCodePoints = 12;
    private const string HealthCheckService = "healthcheck";

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
            .Select(s =>
            {
                string normalizedService = NormalizeService(s.Service);
                bool hasValidLabel = IsValidServiceLabel(normalizedService);
                return new NormalizedSample(normalizedService, s.LatencyMs, s.Offset, hasValidLabel);
            })
            .ToList();

        int count = samples.Count;
        int breaches = 0;
        long overageMs = 0;
        long validSumMs = 0;
        int validCount = 0;
        long maxMs = count > 0 ? long.MinValue : 0;
        int bucketZero = 0;
        int critical = 0;
        int warnOrWorse = 0;
        int consecutiveBreaches = 0;
        int spikeSteps = 0;
        int invalidLabels = 0;
        int exempt = 0;
        int regressed = 0;

        NormalizedSample? previousSample = null;
        bool previousBreached = false;
        long? earlierMinMs = null;

        foreach (NormalizedSample sample in samples)
        {
            if (sample.HasValidLabel)
            {
                validSumMs += sample.LatencyMs;
                validCount++;
            }
            else
            {
                invalidLabels++;
            }

            if (sample.LatencyMs > maxMs)
            {
                maxMs = sample.LatencyMs;
            }

            bool isBucketZero = RemEuclid(sample.Offset, BucketDivisor) == 0;
            if (isBucketZero)
            {
                bucketZero++;
            }

            bool isRawBreach = IsRawBreach(sample.LatencyMs, slaMs);
            bool isExempt = isRawBreach && IsMaintenanceExempt(sample.Service, isBucketZero);
            if (isExempt)
            {
                exempt++;
            }

            bool isBreach = isRawBreach && !isExempt;
            if (isBreach)
            {
                breaches++;
                overageMs += sample.LatencyMs - slaMsInt;
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

            if (earlierMinMs.HasValue)
            {
                if (earlierMinMs.Value + RegressionThresholdMs < sample.LatencyMs)
                {
                    regressed++;
                }

                if (sample.LatencyMs < earlierMinMs.Value)
                {
                    earlierMinMs = sample.LatencyMs;
                }
            }
            else
            {
                earlierMinMs = sample.LatencyMs;
            }

            previousSample = sample;
            previousBreached = isBreach;
        }

        long meanMs = validCount > 0
            ? RoundHalfToEven((double)validSumMs / validCount)
            : 0;

        string status = DetermineStatus(consecutiveBreaches, critical, breaches, invalidLabels);

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
            SpikeSteps: spikeSteps,
            InvalidLabels: invalidLabels,
            Exempt: exempt,
            Regressed: regressed,
            Status: status
        );
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

    private static bool IsRawBreach(long latencyMs, double slaMs) =>
        (double)latencyMs > slaMs;

    private static bool IsMaintenanceExempt(string normalizedService, bool isBucketZero) =>
        isBucketZero && string.Equals(normalizedService, HealthCheckService, StringComparison.Ordinal);

    private static LatencySeverity ClassifySeverity(long latencyMs) => latencyMs switch
    {
        < 200 => LatencySeverity.Ok,
        <= 500 => LatencySeverity.Warn,
        <= 1000 => LatencySeverity.Slow,
        _ => LatencySeverity.Critical
    };

    private static string NormalizeService(string service) =>
        service.Trim().ToLowerInvariant();

    private static bool IsValidServiceLabel(string normalizedService)
    {
        int codePoints = CountCodePoints(normalizedService);
        return codePoints is >= MinServiceCodePoints and <= MaxServiceCodePoints;
    }

    private static int CountCodePoints(string value)
    {
        int count = 0;
        foreach (Rune _ in value.EnumerateRunes())
        {
            count++;
        }

        return count;
    }

    private static long RoundHalfToEven(double value) =>
        (long)Math.Round(value, MidpointRounding.ToEven);

    private static long RemEuclid(long dividend, long divisor)
    {
        long remainder = dividend % divisor;
        return remainder < 0 ? remainder + divisor : remainder;
    }
}
