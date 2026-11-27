using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace ReleaseGate;

public sealed record ReleaseInput(
    [property: JsonPropertyName("min_range")] string MinRange,
    [property: JsonPropertyName("budget_mb")] double BudgetMb,
    [property: JsonPropertyName("artifacts")] List<ArtifactInput> Artifacts
);

public sealed record ArtifactInput(
    [property: JsonPropertyName("raw_path")] string RawPath,
    [property: JsonPropertyName("channel")] string Channel,
    [property: JsonPropertyName("size_kb")] long SizeKb
);

public sealed record ReleaseSummary(
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("eligible")] int Eligible,
    [property: JsonPropertyName("oversize")] int Oversize,
    [property: JsonPropertyName("total_kb")] long TotalKb,
    [property: JsonPropertyName("max_kb")] long MaxKb,
    [property: JsonPropertyName("consecutive_rejects")] int ConsecutiveRejects,
    [property: JsonPropertyName("freeze")] bool Freeze,
    [property: JsonPropertyName("exempt")] int Exempt,
    [property: JsonPropertyName("eligible_kb")] long EligibleKb,
    [property: JsonPropertyName("within_budget")] bool WithinBudget
);

public readonly record struct SemVer(long Major, long Minor, long Patch, string? Prerelease)
    : IComparable<SemVer>
{
    public bool IsPrerelease => !string.IsNullOrEmpty(Prerelease);

    public static bool TryParse(string input, out SemVer version)
    {
        version = default;
        if (string.IsNullOrEmpty(input))
        {
            return false;
        }

        string corePart = input;
        string? prereleasePart = null;

        int dashIndex = input.IndexOf('-');
        if (dashIndex >= 0)
        {
            corePart = input[..dashIndex];
            prereleasePart = input[(dashIndex + 1)..];
            if (!IsValidPrerelease(prereleasePart))
            {
                return false;
            }
        }

        string[] coreSegments = corePart.Split('.');
        if (coreSegments.Length != 3)
        {
            return false;
        }

        if (!TryParseNumericIdentifier(coreSegments[0], out long major) ||
            !TryParseNumericIdentifier(coreSegments[1], out long minor) ||
            !TryParseNumericIdentifier(coreSegments[2], out long patch))
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

        if (!IsPrerelease && !other.IsPrerelease) return 0;
        if (!IsPrerelease) return 1;
        if (!other.IsPrerelease) return -1;

        string[] leftIds = Prerelease!.Split('.');
        string[] rightIds = other.Prerelease!.Split('.');
        int minLen = Math.Min(leftIds.Length, rightIds.Length);

        for (int i = 0; i < minLen; i++)
        {
            bool leftIsNum = TryParseNumericIdentifier(leftIds[i], out long leftNum);
            bool rightIsNum = TryParseNumericIdentifier(rightIds[i], out long rightNum);

            if (leftIsNum && rightIsNum)
            {
                cmp = leftNum.CompareTo(rightNum);
            }
            else if (leftIsNum)
            {
                cmp = -1;
            }
            else if (rightIsNum)
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

    private static bool IsValidPrerelease(string prerelease)
    {
        if (string.IsNullOrEmpty(prerelease))
        {
            return false;
        }

        string[] identifiers = prerelease.Split('.');
        foreach (string id in identifiers)
        {
            if (string.IsNullOrEmpty(id))
            {
                return false;
            }

            bool allDigits = true;
            foreach (char c in id)
            {
                bool validChar = (c >= '0' && c <= '9')
                    || (c >= 'a' && c <= 'z')
                    || (c >= 'A' && c <= 'Z')
                    || c == '-';
                if (!validChar)
                {
                    return false;
                }
                if (c < '0' || c > '9')
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

    private static bool TryParseNumericIdentifier(string segment, out long value)
    {
        value = 0;
        if (string.IsNullOrEmpty(segment))
        {
            return false;
        }
        if (segment.Length > 1 && segment[0] == '0')
        {
            return false;
        }
        foreach (char c in segment)
        {
            if (c < '0' || c > '9')
            {
                return false;
            }
        }
        return long.TryParse(segment, out value);
    }
}

public sealed class CaretSemVerRange
{
    private readonly SemVer _lowerInclusive;
    private readonly SemVer _upperExclusive;

    private CaretSemVerRange(SemVer lowerInclusive, SemVer upperExclusive)
    {
        _lowerInclusive = lowerInclusive;
        _upperExclusive = upperExclusive;
    }

    public static bool TryParse(string rangeText, out CaretSemVerRange? range)
    {
        range = null;
        if (string.IsNullOrWhiteSpace(rangeText))
        {
            return false;
        }

        string trimmed = rangeText.Trim();
        if (!trimmed.StartsWith('^'))
        {
            return false;
        }

        string versionPart = trimmed[1..].Trim();
        if (!SemVer.TryParse(versionPart, out SemVer baseVersion) || baseVersion.IsPrerelease)
        {
            return false;
        }

        SemVer upper = baseVersion.Major > 0
            ? new SemVer(baseVersion.Major + 1, 0, 0, null)
            : baseVersion.Minor > 0
                ? new SemVer(0, baseVersion.Minor + 1, 0, null)
                : new SemVer(0, 0, baseVersion.Patch + 1, null);

        range = new CaretSemVerRange(baseVersion, upper);
        return true;
    }

    public bool IsSatisfiedBy(SemVer version)
    {
        if (version.IsPrerelease)
        {
            return false;
        }

        return version.CompareTo(_lowerInclusive) >= 0
            && version.CompareTo(_upperExclusive) < 0;
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

        int initialSlashes = 0;
        while (initialSlashes < path.Length && path[initialSlashes] == '/')
        {
            initialSlashes++;
        }

        // POSIX preserves exactly two leading slashes; 3 or more collapse to 1.
        if (initialSlashes > 2)
        {
            initialSlashes = 1;
        }

        string[] rawSegments = path.Split('/');
        List<string> resolved = new(rawSegments.Length);

        foreach (string segment in rawSegments)
        {
            if (string.IsNullOrEmpty(segment) || segment == ".")
            {
                continue;
            }

            if (segment == "..")
            {
                if (resolved.Count > 0 && resolved[^1] != "..")
                {
                    resolved.RemoveAt(resolved.Count - 1);
                }
                else if (initialSlashes == 0)
                {
                    resolved.Add("..");
                }
            }
            else
            {
                resolved.Add(segment);
            }
        }

        string joined = string.Join('/', resolved);
        if (initialSlashes > 0)
        {
            return new string('/', initialSlashes) + joined;
        }

        return joined.Length > 0 ? joined : ".";
    }

    public static string Basename(string posixPath)
    {
        if (string.IsNullOrEmpty(posixPath))
        {
            return string.Empty;
        }

        int lastSlash = posixPath.LastIndexOf('/');
        return lastSlash < 0 ? posixPath : posixPath[(lastSlash + 1)..];
    }

    public static string Dirname(string posixPath)
    {
        if (string.IsNullOrEmpty(posixPath))
        {
            return string.Empty;
        }

        int lastSlash = posixPath.LastIndexOf('/');
        if (lastSlash < 0)
        {
            return string.Empty;
        }

        string head = posixPath[..lastSlash].TrimEnd('/');
        return string.IsNullOrEmpty(head) && posixPath.StartsWith('/') ? "/" : head;
    }
}

public static partial class Program
{
    private static readonly HashSet<string> AllowedChannels = new(StringComparer.Ordinal)
    {
        "stable",
        "beta",
        "lts"
    };

    [GeneratedRegex(@"\A[a-z0-9-]+/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?\z", RegexOptions.CultureInvariant)]
    private static partial Regex ValidPathRegex();

    public static int Main()
    {
        string inputText = Console.In.ReadToEnd();
        ReleaseInput? input = JsonSerializer.Deserialize<ReleaseInput>(inputText);
        if (input is null)
        {
            throw new InvalidOperationException("Failed to deserialize input JSON.");
        }

        CaretSemVerRange.TryParse(input.MinRange, out CaretSemVerRange? minRange);

        List<ArtifactInput> artifacts = input.Artifacts ?? [];
        int total = artifacts.Count;
        int eligible = 0;
        int oversize = 0;
        int exempt = 0;
        int consecutiveRejects = 0;
        long totalKb = 0;
        long eligibleKb = 0;
        long maxKb = 0;
        bool hasArtifacts = total > 0;
        bool prevRejected = false;

        for (int i = 0; i < total; i++)
        {
            ArtifactInput artifact = artifacts[i];
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

            (bool isEligible, bool usedExemption) = EvaluateArtifact(artifact, isOversize, minRange);
            if (usedExemption)
            {
                exempt++;
            }

            if (isEligible)
            {
                eligible++;
                eligibleKb += artifact.SizeKb;
                prevRejected = false;
            }
            else
            {
                if (prevRejected)
                {
                    consecutiveRejects++;
                }
                prevRejected = true;
            }
        }

        double budgetKb = input.BudgetMb * 1024.0;
        ReleaseSummary summary = new(
            Total: total,
            Eligible: eligible,
            Oversize: oversize,
            TotalKb: totalKb,
            MaxKb: hasArtifacts ? maxKb : 0,
            ConsecutiveRejects: consecutiveRejects,
            Freeze: consecutiveRejects >= 2,
            Exempt: exempt,
            EligibleKb: eligibleKb,
            WithinBudget: eligibleKb <= budgetKb
        );

        Console.WriteLine(JsonSerializer.Serialize(summary));
        return 0;
    }

    private static string ClassifySizeTier(long sizeKb) => sizeKb switch
    {
        < 100 => "tiny",
        <= 1000 => "standard",
        <= 5000 => "large",
        _ => "oversize"
    };

    private static (bool IsEligible, bool UsedExemption) EvaluateArtifact(
        ArtifactInput artifact,
        bool isOversize,
        CaretSemVerRange? minRange)
    {
        if (isOversize)
        {
            return (false, false);
        }

        string decoded = Uri.UnescapeDataString(artifact.RawPath ?? string.Empty);
        string norm = PosixPath.Normalize(decoded);

        if (!ValidPathRegex().IsMatch(norm))
        {
            return (false, false);
        }

        string channel = artifact.Channel ?? string.Empty;
        if (!AllowedChannels.Contains(channel))
        {
            return (false, false);
        }

        string pkg = PosixPath.Dirname(norm);
        string ver = PosixPath.Basename(norm);
        if (!SemVer.TryParse(ver, out SemVer parsedVer))
        {
            return (false, false);
        }

        bool satisfiesRange = minRange is not null && minRange.IsSatisfiedBy(parsedVer);
        bool isLtsSecurityExempt = channel == "lts"
            && pkg.Contains("security", StringComparison.Ordinal)
            && !parsedVer.IsPrerelease;

        bool isEligible = satisfiesRange || isLtsSecurityExempt;
        bool usedExemption = isLtsSecurityExempt && !satisfiesRange;
        return (isEligible, usedExemption);
    }
}
