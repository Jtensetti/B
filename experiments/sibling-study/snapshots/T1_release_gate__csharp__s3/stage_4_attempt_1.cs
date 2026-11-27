using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace ReleaseGate;

public sealed record ArtifactInput(
    [property: JsonPropertyName("raw_path")] string RawPath,
    [property: JsonPropertyName("channel")] string Channel,
    [property: JsonPropertyName("size_kb")] long SizeKb);

public sealed record ReleaseGateInput(
    [property: JsonPropertyName("min_range")] string MinRange,
    [property: JsonPropertyName("budget_mb")] double BudgetMb,
    [property: JsonPropertyName("artifacts")] List<ArtifactInput> Artifacts);

public sealed record ReleaseGateOutput(
    [property: JsonPropertyName("total")] int Total,
    [property: JsonPropertyName("eligible")] int Eligible,
    [property: JsonPropertyName("oversize")] int Oversize,
    [property: JsonPropertyName("total_kb")] long TotalKb,
    [property: JsonPropertyName("max_kb")] long MaxKb,
    [property: JsonPropertyName("consecutive_rejects")] int ConsecutiveRejects,
    [property: JsonPropertyName("freeze")] bool Freeze,
    [property: JsonPropertyName("exempt")] int Exempt,
    [property: JsonPropertyName("eligible_kb")] long EligibleKb,
    [property: JsonPropertyName("within_budget")] bool WithinBudget);

public sealed record ParsedArtifact(
    ArtifactInput Source,
    string NormalizedPath,
    string Package,
    string VersionString,
    SemVer? Version,
    string SizeTier,
    bool HasValidFormat,
    bool IsEligible,
    bool IsExempt);

public readonly record struct SemVer(int Major, int Minor, int Patch, string? Prerelease) : IComparable<SemVer>
{
    public bool IsPrerelease => !string.IsNullOrEmpty(Prerelease);

    public static bool TryParse(string input, out SemVer version)
    {
        version = default;
        if (string.IsNullOrEmpty(input))
        {
            return false;
        }

        string core = input;
        string? prerelease = null;

        int dashIndex = input.IndexOf('-');
        if (dashIndex >= 0)
        {
            core = input[..dashIndex];
            prerelease = input[(dashIndex + 1)..];
            if (!IsValidPrerelease(prerelease))
            {
                return false;
            }
        }

        string[] parts = core.Split('.');
        if (parts.Length != 3)
        {
            return false;
        }

        if (!TryParseNumericIdentifier(parts[0], out int major) ||
            !TryParseNumericIdentifier(parts[1], out int minor) ||
            !TryParseNumericIdentifier(parts[2], out int patch))
        {
            return false;
        }

        version = new SemVer(major, minor, patch, prerelease);
        return true;
    }

    private static bool TryParseNumericIdentifier(string token, out int value)
    {
        value = 0;
        if (token.Length == 0 || (token.Length > 1 && token[0] == '0'))
        {
            return false;
        }

        foreach (char c in token)
        {
            if (c < '0' || c > '9')
            {
                return false;
            }
        }

        return int.TryParse(token, out value);
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
                bool isValidChar = isDigit || c is >= 'a' and <= 'z' or >= 'A' and <= 'Z' or '-';
                if (!isValidChar)
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

    public int CompareTo(SemVer other)
    {
        int cmp = Major.CompareTo(other.Major);
        if (cmp != 0)
        {
            return cmp;
        }

        cmp = Minor.CompareTo(other.Minor);
        if (cmp != 0)
        {
            return cmp;
        }

        cmp = Patch.CompareTo(other.Patch);
        if (cmp != 0)
        {
            return cmp;
        }

        if (!IsPrerelease && !other.IsPrerelease)
        {
            return 0;
        }

        if (!IsPrerelease)
        {
            return 1;
        }

        if (!other.IsPrerelease)
        {
            return -1;
        }

        string[] a = Prerelease!.Split('.');
        string[] b = other.Prerelease!.Split('.');
        int minLen = Math.Min(a.Length, b.Length);

        for (int i = 0; i < minLen; i++)
        {
            bool aNum = TryParseNumericIdentifier(a[i], out int aVal);
            bool bNum = TryParseNumericIdentifier(b[i], out int bVal);

            if (aNum && bNum)
            {
                cmp = aVal.CompareTo(bVal);
            }
            else if (aNum)
            {
                cmp = -1;
            }
            else if (bNum)
            {
                cmp = 1;
            }
            else
            {
                cmp = string.CompareOrdinal(a[i], b[i]);
            }

            if (cmp != 0)
            {
                return cmp;
            }
        }

        return a.Length.CompareTo(b.Length);
    }

    public static bool operator >=(SemVer left, SemVer right) => left.CompareTo(right) >= 0;
    public static bool operator <=(SemVer left, SemVer right) => left.CompareTo(right) <= 0;
    public static bool operator <(SemVer left, SemVer right) => left.CompareTo(right) < 0;
    public static bool operator >(SemVer left, SemVer right) => left.CompareTo(right) > 0;
}

public static class SemVerRange
{
    public static bool SatisfiesCaret(SemVer version, string range)
    {
        if (version.IsPrerelease)
        {
            return false;
        }

        string trimmed = range.Trim();
        if (!trimmed.StartsWith('^'))
        {
            return false;
        }

        string baseVersionStr = trimmed[1..].Trim();
        if (!SemVer.TryParse(baseVersionStr, out SemVer lower) || lower.IsPrerelease)
        {
            return false;
        }

        SemVer upper = lower.Major > 0
            ? new SemVer(lower.Major + 1, 0, 0, null)
            : lower.Minor > 0
                ? new SemVer(0, lower.Minor + 1, 0, null)
                : new SemVer(0, 0, lower.Patch + 1, null);

        return version >= lower && version < upper;
    }
}

public static class PosixPath
{
    public static string DecodeAndNormalize(string rawPath)
    {
        string decoded = Uri.UnescapeDataString(rawPath);
        return Normalize(decoded);
    }

    public static string Normalize(string path)
    {
        if (string.IsNullOrEmpty(path))
        {
            return ".";
        }

        bool isAbsolute = path.StartsWith('/');
        string[] segments = path.Split('/');
        List<string> stack = new();

        foreach (string segment in segments)
        {
            if (segment.Length == 0 || segment == ".")
            {
                continue;
            }

            if (segment == "..")
            {
                if (stack.Count > 0 && stack[^1] != "..")
                {
                    stack.RemoveAt(stack.Count - 1);
                }
                else if (!isAbsolute)
                {
                    stack.Add("..");
                }
            }
            else
            {
                stack.Add(segment);
            }
        }

        if (isAbsolute)
        {
            return stack.Count == 0 ? "/" : "/" + string.Join('/', stack);
        }

        return stack.Count == 0 ? "." : string.Join('/', stack);
    }

    public static string BaseName(string normalizedPath)
    {
        int slash = normalizedPath.LastIndexOf('/');
        return slash < 0 ? normalizedPath : normalizedPath[(slash + 1)..];
    }

    public static string DirName(string normalizedPath)
    {
        int slash = normalizedPath.LastIndexOf('/');
        if (slash < 0)
        {
            return ".";
        }

        return slash == 0 ? "/" : normalizedPath[..slash];
    }
}

public static class Gatekeeper
{
    private static readonly Regex ValidPathRegex = new(
        @"\A[a-z0-9-]+/[0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?\z",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    private static readonly HashSet<string> ValidChannels = new(StringComparer.Ordinal)
    {
        "stable",
        "beta",
        "lts"
    };

    public static string ClassifySizeTier(long sizeKb) => sizeKb switch
    {
        < 100 => "tiny",
        <= 1000 => "standard",
        <= 5000 => "large",
        _ => "oversize"
    };

    public static ParsedArtifact EvaluateArtifact(ArtifactInput artifact, string minRange)
    {
        string normalized = PosixPath.DecodeAndNormalize(artifact.RawPath);
        string package = PosixPath.DirName(normalized);
        string versionStr = PosixPath.BaseName(normalized);
        string sizeTier = ClassifySizeTier(artifact.SizeKb);

        bool hasValidFormat = ValidPathRegex.IsMatch(normalized) && ValidChannels.Contains(artifact.Channel);

        SemVer? parsedVersion = null;
        bool isEligible = false;
        bool isExempt = false;
        if (hasValidFormat && SemVer.TryParse(versionStr, out SemVer version))
        {
            parsedVersion = version;
            bool notOversize = sizeTier != "oversize";
            bool satisfiesRange = notOversize && SemVerRange.SatisfiesCaret(version, minRange);
            bool matchesLtsSecurityExemption =
                notOversize &&
                artifact.Channel == "lts" &&
                package.Contains("security", StringComparison.Ordinal) &&
                !version.IsPrerelease;

            isExempt = !satisfiesRange && matchesLtsSecurityExemption;
            isEligible = satisfiesRange || isExempt;
        }

        return new ParsedArtifact(
            artifact,
            normalized,
            package,
            versionStr,
            parsedVersion,
            sizeTier,
            hasValidFormat,
            isEligible,
            isExempt);
    }

    private const double KilobytesPerMegabyte = 1024.0;

    public static ReleaseGateOutput Evaluate(ReleaseGateInput input)
    {
        int total = input.Artifacts.Count;
        int eligible = 0;
        int oversize = 0;
        int exempt = 0;
        long totalKb = 0;
        long maxKb = 0;
        long eligibleKb = 0;
        int consecutiveRejects = 0;
        bool prevRejected = false;

        for (int i = 0; i < total; i++)
        {
            ArtifactInput artifact = input.Artifacts[i];
            ParsedArtifact evaluated = EvaluateArtifact(artifact, input.MinRange);

            if (evaluated.IsEligible)
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

            if (evaluated.IsExempt)
            {
                exempt++;
            }

            if (evaluated.SizeTier == "oversize")
            {
                oversize++;
            }

            totalKb += artifact.SizeKb;
            if (i == 0 || artifact.SizeKb > maxKb)
            {
                maxKb = artifact.SizeKb;
            }
        }

        bool freeze = consecutiveRejects >= 2;
        bool withinBudget = eligibleKb <= input.BudgetMb * KilobytesPerMegabyte;
        return new ReleaseGateOutput(
            total,
            eligible,
            oversize,
            totalKb,
            maxKb,
            consecutiveRejects,
            freeze,
            exempt,
            eligibleKb,
            withinBudget);
    }
}

public static class Program
{
    public static int Main()
    {
        string inputText = Console.In.ReadToEnd();
        ReleaseGateInput? input = JsonSerializer.Deserialize<ReleaseGateInput>(inputText);
        if (input is null)
        {
            Console.Error.WriteLine("Failed to parse input JSON.");
            return 1;
        }

        ReleaseGateOutput output = Gatekeeper.Evaluate(input);
        Console.WriteLine(JsonSerializer.Serialize(output));
        return 0;
    }
}
