// Driver: reads a JSON array of weekday names on stdin and prints Overtime.Multiplier for each.
// The item "holiday" gives Overtime.Holiday() instead.
using System.Text.Json;
using Rules;

var input = await Console.In.ReadToEndAsync();
var days = JsonSerializer.Deserialize<List<string>>(input) ?? new List<string>();
var results = new List<Dictionary<string, object?>>();
foreach (var day in days)
{
    try
    {
        var value = day == "holiday" ? Overtime.Holiday() : Overtime.Multiplier(day);
        results.Add(new() { ["ok"] = true, ["value"] = value, ["error"] = null });
    }
    catch (ArgumentException e)
    {
        results.Add(new() { ["ok"] = false, ["value"] = 0.0, ["error"] = e.Message });
    }
}
Console.WriteLine(JsonSerializer.Serialize(results));
