namespace Tax;

/// VAT rules. Maintained by the finance team.
public static class Vat
{
    static readonly Dictionary<string, double> Standard = new()
    {
        ["SE"] = 0.25, ["NO"] = 0.25, ["DK"] = 0.25, ["FI"] = 0.255, ["DE"] = 0.19,
        ["NL"] = 0.21, ["PL"] = 0.23, ["FR"] = 0.20, ["ES"] = 0.21, ["IT"] = 0.22,
    };
    static readonly HashSet<string> Eu = new() { "SE", "DK", "FI", "DE", "NL", "PL", "FR", "ES", "IT" };

    /// The standard VAT rate for a country. Throws KeyNotFoundException for unknown countries.
    public static double Rate(string country) =>
        Standard.TryGetValue(country.Trim().ToUpperInvariant(), out var r) ? r
            : throw new KeyNotFoundException("no VAT rate for " + country);

    /// True when a business customer in another EU country pays no VAT (reverse charge) on a sale from Sweden.
    public static bool ReverseCharge(string country, bool business)
    {
        var c = country.Trim().ToUpperInvariant();
        return business && c != "SE" && Eu.Contains(c);
    }
}
