// Driver: reads one key per line on stdin and prints the pay multiplier for each.
// "@holiday" gives Overtime.Holiday(); anything else goes to Overtime.Multiplier,
// and "ERR" is printed when that throws.
using System.Globalization;
using Rules;

var sb = new System.Text.StringBuilder();
string? line;
while ((line = Console.ReadLine()) != null)
{
    try
    {
        double m = line == "@holiday" ? Overtime.Holiday() : Overtime.Multiplier(line);
        sb.Append(m.ToString("R", CultureInfo.InvariantCulture)).Append('\n');
    }
    catch (ArgumentException)
    {
        sb.Append("ERR\n");
    }
}
Console.Out.Write(sb.ToString());
