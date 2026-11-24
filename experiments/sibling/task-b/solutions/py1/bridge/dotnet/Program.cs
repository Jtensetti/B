// Bridge: reads a JSON array of weekday names (or "Holiday") on stdin, writes a JSON array
// of {"value": multiplier} or {"error": message} using Rules.Overtime.
// "Holiday" maps to Overtime.Holiday().
using System.Text.Json;
using Rules;

var weekdays = JsonSerializer.Deserialize<List<string>>(Console.In.ReadToEnd()) ?? new List<string>();
var results = new List<Dictionary<string, object>>();
foreach (var day in weekdays)
{
    try
    {
        double value = day == "Holiday" ? Overtime.Holiday() : Overtime.Multiplier(day);
        results.Add(new Dictionary<string, object> { ["value"] = value });
    }
    catch (ArgumentException e)
    {
        results.Add(new Dictionary<string, object> { ["error"] = e.Message });
    }
}
Console.Out.Write(JsonSerializer.Serialize(results));
