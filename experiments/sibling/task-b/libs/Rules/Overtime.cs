namespace Rules;

/// Pay multipliers from the collective agreement. Maintained by HR.
public static class Overtime
{
    /// Multiplier for a weekday written "Mon".."Sun". Throws ArgumentException for anything else.
    public static double Multiplier(string weekday) => weekday switch
    {
        "Mon" or "Tue" or "Wed" or "Thu" or "Fri" => 1.0,
        "Sat" => 1.5,
        "Sun" => 2.0,
        _ => throw new ArgumentException("unknown weekday " + weekday),
    };

    /// Multiplier for a public holiday, whatever the weekday.
    public static double Holiday() => 2.0;
}
