// Bridge to libs/Packaging. Reads {"requests":[[quantity, packSize], ...]} on stdin and
// writes {"results":[{"ok":true,"value":n} | {"ok":false,"error":"..."}, ...]} on stdout.
using System.Text.Json;
using Packaging;

var doc = JsonDocument.Parse(Console.In.ReadToEnd());
var results = new List<object>();
foreach (var pair in doc.RootElement.GetProperty("requests").EnumerateArray())
{
    int quantity = pair[0].GetInt32();
    int packSize = pair[1].GetInt32();
    try
    {
        results.Add(new { ok = true, value = Packs.RoundUp(quantity, packSize) });
    }
    catch (ArgumentException e)
    {
        results.Add(new { ok = false, error = e.Message });
    }
}
Console.WriteLine(JsonSerializer.Serialize(new { results }));
