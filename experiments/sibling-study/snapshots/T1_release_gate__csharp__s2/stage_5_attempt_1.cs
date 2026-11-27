using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace ReleaseGate;

public sealed record GateInput(
    [property: JsonPropertyName("min_range")] string MinRange,
    [property: JsonPropertyName("budget_mb")] double BudgetMb,
    [property: JsonPropertyName("artifacts")] IReadOnlyList<ArtifactInput> Artifacts
);

public sealed record ArtifactInput(
    [property: JsonPropertyName("raw_path")] string RawPath,
    [property: JsonPropertyName("channel")] string Channel,
    [property: JsonPropertyName("size_kb")] long SizeKb
);

public sealed record GateOutput(
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("eligible")] int Eligible,
    [property: JsonPropertyName("oversize")] int Oversize,
    [property: JsonPropertyName("total_kb")] long TotalKb,
    [property: JsonPropertyName("max_kb")] long MaxKb,
    [property: JsonPropertyName("consecutive_rejects")] int ConsecutiveRejects,
    [property: JsonPropertyName("freeze")] bool Freeze,
    [property: JsonPropertyName("exempt")] int Exempt,
    [property: JsonPropertyName("eligible_kb")] long EligibleKb,
    [property: JsonPropertyName("within_budget")] bool WithinBudget,
    [property: JsonPropertyName("recommended")] string? Recommended
);

public readonly record struct SemVer(long Major, long Minor, long Patch, string? Prerelease)
    : IComparable<SemVer>
{
    public bool IsPrerelease => Prerelease is not null;

    public override string ToString() =>
        Prerelease is null ? $"{Major}.{Minor}.{Patch}" : $"{Major}.{Minor}.{Patch}-{Prerelease}";

    public static bool TryParse(string text, out SemVer version)
    {
        version = default;
        if (string.IsNullOrEmpty(text))
        {
            return false;
        }

        string corePart;
        string? prereleasePart = null;
        int dashIndex = text.IndexOf('-');
        if (dashIndex >= 0)
        {
            corePart = text[..dashIndex];
            prereleasePart = text[(dashIndex + 1)..];
            if (!IsValidPrerelease(prereleasePart))
            {
                return false;
            }
        }
        else
        {
            corePart = text;
        }

        string[] segments = corePart.Split('.');
        if (segments.Length != 3)
        {
            return false;
        }

        if (!TryParseNumericIdentifier(segments[0], out long major) ||
            !TryParseNumericIdentifier(segments[1], out long minor) ||
            !TryParseNumericIdentifier(segments[2], out long patch))
        {
            return false;
        }

        version = new SemVer(major, minor, patch, prereleasePart);
        return true;
    }

    public int CompareTo(SemVer other)
    {
        int cmp = Major.CompareTo(other.Major);
        if (cmp != 0) return cmp;

        cmp = Minor.CompareTo(other.Minor);
        if (cmp != 0) return cmp;

        cmp = Patch.CompareTo(other.Patch);
        if (cmp != 0) return cmp;

        if (Prerelease is null && other.Prerelease is null) return 0;
        if (Prerelease is null) return 1;
        if (other.Prerelease is null) return -1;

        string[] leftIds = Prerelease.Split('.');
        string[] rightIds = other.Prerelease.Split('.');
        int count = Math.Min(leftIds.Length, rightIds.Length);

        for (int i = 0; i < count; i++)
        {
            bool leftNum = TryParseNumericIdentifier(leftIds[i], out long lVal);
            bool rightNum = TryParseNumericIdentifier(rightIds[i], out long rVal);

            if (leftNum && rightNum)
            {
                cmp = lVal.CompareTo(rVal);
            }
            else if (leftNum)
            {
                cmp = -1;
            }
            else if (rightNum)
            {
                cmp = 1;
            }
            else
            {
                cmp = string.CompareOrdinal(leftIds[i], rightIds[i]);
            }

            if (cmp != 0) return cmp;
        }

        return leftIds.Length.CompareTo(rightIds.Length);
    }

    private static bool TryParseNumericIdentifier(string token, out long value)
    {
        value = 0;
        if (token.Length == 0)
        {
            return false;
        }

        if (token.Length > 1 && token[0] == '0')
        {
            return false;
        }

        for (int i = 0; i < token.Length; i++)
        {
            if (token[i] is < '0' or > '9')
            {
                return false;
            }
        }

        return long.TryParse(token, out value);
    }

    private static bool IsValidPrerelease(string prerelease)
    {
        if (string.IsNullOrEmpty(prerelease))
        {
            return false;
        }

        string[] identifiers = prerelease.Split('.');
        foreach (string id in identifiers)
        {
            if (id.Length == 0)
            {
                return false;
            }

            bool allDigits = true;
            foreach (char c in id)
            {
                bool isDigit = c is >= '0' and <= '9';
                bool isAllowed = isDigit || c is (>= 'a' and <= 'z') or (>= 'A' and <= 'Z') or '-';
                if (!isAllowed)
                {
                    return false;
                }

                if (!isDigit)
                {
                    allDigits = false;
                }
            }

            if (allDigits && id.Length > 1 && id[0] == '0')
            {
                return false;
            }
        }

        return true;
    }
}

public readonly record struct CaretRange(SemVer LowerBound, SemVer UpperBound)
{
    public static bool TryParse(string text, out CaretRange range)
    {
        range = default;
        if (string.IsNullOrWhiteSpace(text))
        {
            return false;
        }

        string trimmed = text.Trim();
        if (!trimmed.StartsWith('^'))
        {
            return false;
        }

        if (!SemVer.TryParse(trimmed[1..], out SemVer baseVer) || baseVer.IsPrerelease)
        {
            return false;
        }

        SemVer upper = baseVer.Major > 0
            ? new SemVer(baseVer.Major + 1, 0, 0, null)
            : baseVer.Minor > 0
                ? new SemVer(0, baseVer.Minor + 1, 0, null)
                : new SemVer(0, 0, baseVer.Patch + 1, null);

        range = new CaretRange(baseVer, upper);
        return true;
    }

    public bool IsSatisfiedBy(SemVer version)
    {
        if (version.IsPrerelease)
        {
            return false;
        }

        return version.CompareTo(LowerBound) >= 0 && version.CompareTo(UpperBound) < 0;
    }
}

public static class PosixPath
{
    public static string Normalize(string path)
    {
        if (string.IsNullOrEmpty(path))
        {
            return ".";
        }

        bool isAbsolute = path[0] == '/';
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

        string joined = string.Join('/', segments);
        if (isAbsolute)
        {
            return "/" + joined;
        }

        return joined.Length == 0 ? "." : joined;
    }

    public static (string Dirname, string Basename) Split(string normalizedPath)
    {
        int slashIndex = normalizedPath.LastIndexOf('/');
        if (slashIndex < 0)
        {
            return (".", normalizedPath);
        }

        if (slashIndex == 0)
        {
            return ("/", normalizedPath[1..]);
        }

        return (normalizedPath[..slashIndex], normalizedPath[(slashIndex + 1)..]);
    }
}

public static partial class Program
{
    private static readonly HashSet<string> ValidChannels = new(StringComparer.Ordinal)
    {
        "stable",
        "beta",
        "lts"
    };

    [GeneratedRegex(@"\A[a-z0-9-]+/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?\z", RegexOptions.CultureInvariant)]
    private static partial Regex ValidPathRegex();

    public static void Main()
    {
        string rawJson = Console.In.ReadToEnd();
        GateInput input = JsonSerializer.Deserialize<GateInput>(rawJson)
            ?? throw new InvalidOperationException("Failed to deserialize input JSON.");

        GateOutput output = Evaluate(input);
        Console.WriteLine(JsonSerializer.Serialize(output));
    }

    private static GateOutput Evaluate(GateInput input)
    {
        bool hasValidRange = CaretRange.TryParse(input.MinRange, out CaretRange minRange);

        int total = input.Artifacts.Count;
        int eligible = 0;
        int oversize = 0;
        int exempt = 0;
        long totalKb = 0;
        long maxKb = 0;
        long eligibleKb = 0;
        int consecutiveRejects = 0;
        bool prevRejected = false;
        SemVer? highestEligible = null;

        for (int i = 0; i < input.Artifacts.Count; i++)
        {
            ArtifactInput artifact = input.Artifacts[i];
            totalKb += artifact.SizeKb;
            if (i == 0 || artifact.SizeKb > maxKb)
            {
                maxKb = artifact.SizeKb;
            }

            string sizeTier = ClassifySizeTier(artifact.SizeKb);
            bool isOversize = sizeTier == "oversize";
            if (isOversize)
            {
                oversize++;
            }

            string decoded = Uri.UnescapeDataString(artifact.RawPath);
            string normalized = PosixPath.Normalize(decoded);
            (string pkg, string ver) = PosixPath.Split(normalized);

            bool isValidFormat = !string.IsNullOrEmpty(pkg)
                && ValidPathRegex().IsMatch(normalized)
                && ValidChannels.Contains(artifact.Channel);

            bool hasValidSemVer = SemVer.TryParse(ver, out SemVer semVer);

            bool satisfiesRange = !isOversize &&
                isValidFormat &&
                hasValidRange &&
                hasValidSemVer &&
                minRange.IsSatisfiedBy(semVer);

            bool isLtsSecurityExempt = !isOversize &&
                isValidFormat &&
                artifact.Channel == "lts" &&
                pkg.Contains("security", StringComparison.Ordinal) &&
                hasValidSemVer &&
                !semVer.IsPrerelease;

            bool isEligible = satisfiesRange || isLtsSecurityExempt;
            if (isLtsSecurityExempt && !satisfiesRange)
            {
                exempt++;
            }

            if (isEligible)
            {
                eligible++;
                eligibleKb += artifact.SizeKb;
                if (highestEligible is null || semVer.CompareTo(highestEligible.Value) > 0)
                {
                    highestEligible = semVer;
                }
            }
            else if (i > 0 && prevRejected)
            {
                consecutiveRejects++;
            }

            prevRejected = !isEligible;
        }

        bool freeze = consecutiveRejects >= 2;
        double budgetKb = input.BudgetMb * 1024.0;
        bool withinBudget = eligibleKb <= budgetKb;
        string? recommended = highestEligible?.ToString();
        return new GateOutput(
            total,
            eligible,
            oversize,
            totalKb,
            maxKb,
            consecutiveRejects,
            freeze,
            exempt,
            eligibleKb,
            withinBudget,
            recommended
        );
    }

    private static string ClassifySizeTier(long sizeKb) => sizeKb switch
    {
        < 100 => "tiny",
        <= 1000 => "standard",
        <= 5000 => "large",
        _ => "oversize"
    };
}
