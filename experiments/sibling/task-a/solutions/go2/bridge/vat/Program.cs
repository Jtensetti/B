// Reads a JSON array of {"Country","Business"} on stdin, writes a JSON array of
// {"Rate","Reverse","Error"} using Tax.Vat from libs/Tax.
using System.Text.Json;
using Tax;

var queries = JsonSerializer.Deserialize<List<Query>>(Console.In.ReadToEnd()) ?? new List<Query>();
var results = queries.Select(q =>
{
    try
    {
        return new Result(Vat.Rate(q.Country), Vat.ReverseCharge(q.Country, q.Business), null);
    }
    catch (Exception e)
    {
        return new Result(0, false, e.Message);
    }
}).ToList();
Console.Out.Write(JsonSerializer.Serialize(results));

record Query(string Country, bool Business);
record Result(double Rate, bool Reverse, string? Error);
