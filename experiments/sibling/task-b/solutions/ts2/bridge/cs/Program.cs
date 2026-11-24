// Bridge: reads a JSON array of weekday names (or "Holiday") on stdin, prints a JSON array of Overtime.Multiplier values.
using System.Text.Json;
using Rules;

var input = Console.In.ReadToEnd();
var days = JsonSerializer.Deserialize<string[]>(input) ?? Array.Empty<string>();
var result = days.Select(d => d == "Holiday" ? Overtime.Holiday() : Overtime.Multiplier(d)).ToArray();
Console.WriteLine(JsonSerializer.Serialize(result));
