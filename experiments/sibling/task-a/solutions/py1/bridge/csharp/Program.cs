// Bridge to libs/Tax (Vat). Reads {"items": [{"country": "DE", "business": true}, ...]} on stdin and
// writes {"results": [{"ok": true, "rate": 0.19, "reverse": false}, ...]} on stdout.
using System.Text.Json.Nodes;

var doc = JsonNode.Parse(Console.In.ReadToEnd())!;
var results = new JsonArray();
foreach (var item in doc["items"]!.AsArray())
{
    var country = item!["country"]!.GetValue<string>();
    var business = item["business"]!.GetValue<bool>();
    try
    {
        var reverse = Tax.Vat.ReverseCharge(country, business);
        var rate = reverse ? 0.0 : Tax.Vat.Rate(country);
        results.Add(new JsonObject { ["ok"] = true, ["rate"] = rate, ["reverse"] = reverse });
    }
    catch (Exception)
    {
        results.Add(new JsonObject { ["ok"] = false, ["rate"] = 0.0, ["reverse"] = false });
    }
}
Console.WriteLine(new JsonObject { ["results"] = results }.ToJsonString());
