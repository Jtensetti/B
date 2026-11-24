// Line bridge for libs/Rules: one weekday (or "holiday") per stdin line, one multiplier per stdout line.
using System.Globalization;
using Rules;

string? line;
while ((line = Console.ReadLine()) != null)
{
    try
    {
        var day = line.Trim();
        var m = day == "holiday" ? Overtime.Holiday() : Overtime.Multiplier(day);
        Console.WriteLine(m.ToString("R", CultureInfo.InvariantCulture));
    }
    catch (Exception e)
    {
        Console.WriteLine("ERR " + e.Message);
    }
}
