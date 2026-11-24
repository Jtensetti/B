using System.Text.Json;
using Tax;

// Reads a JSON array of {"country","business"} and prints a JSON array of {"ok","rate","reverse"}.
var input = Console.In.ReadToEnd();
var reqs = JsonSerializer.Deserialize<List<Req>>(input) ?? new List<Req>();
var outList = new List<Resp>();
foreach (var r in reqs)
{
    bool reverse = Vat.ReverseCharge(r.country, r.business);
    double rate = 0;
    bool ok = true;
    try
    {
        rate = Vat.Rate(r.country);
    }
    catch (KeyNotFoundException)
    {
        ok = false;
    }
    outList.Add(new Resp(ok, rate, reverse));
}
Console.WriteLine(JsonSerializer.Serialize(outList));

record Req(string country, bool business);
record Resp(bool ok, double rate, bool reverse);
