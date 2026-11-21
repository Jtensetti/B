// B's v0.1 .NET boundary: a deliberately tiny, allowlisted JSON-lines protocol.
// Do not expose arbitrary reflection or process execution through this adapter.
using System.Text.Json;

static class Program
{
    static int Main()
    {
        string? line;
        while ((line = Console.ReadLine()) is not null)
        {
            try
            {
                using var doc = JsonDocument.Parse(line);
                var request = doc.RootElement;
                string type = request.GetProperty("type").GetString() ?? "";
                string method = request.GetProperty("method").GetString() ?? "";
                var args = request.GetProperty("args").EnumerateArray().ToArray();
                if (type != "System.Math") throw new InvalidOperationException("Type not allowlisted");
                double Number(int n)
                {
                    if (n >= args.Length || args[n].ValueKind != JsonValueKind.Number)
                        throw new ArgumentException($"Argument {n + 1} must be numeric");
                    double value = args[n].GetDouble();
                    if (!double.IsFinite(value)) throw new ArgumentException("Non-finite numbers are not supported");
                    return value;
                }
                int Arity(int expected)
                {
                    if (args.Length != expected) throw new ArgumentException($"Expected {expected} argument(s)");
                    return expected;
                }
                double result = method switch
                {
                    "Sqrt" when Arity(1) == 1 => Math.Sqrt(Number(0)),
                    "Pow" when Arity(2) == 2 => Math.Pow(Number(0), Number(1)),
                    "Abs" when Arity(1) == 1 => Math.Abs(Number(0)),
                    "Min" when Arity(2) == 2 => Math.Min(Number(0), Number(1)),
                    "Max" when Arity(2) == 2 => Math.Max(Number(0), Number(1)),
                    _ => throw new InvalidOperationException("Method not allowlisted")
                };
                if (!double.IsFinite(result)) throw new ArithmeticException("Non-finite output rejected");
                Console.WriteLine(JsonSerializer.Serialize(new { ok = true, value = result }));
            }
            catch (Exception ex)
            {
                Console.WriteLine(JsonSerializer.Serialize(new { ok = false, error = ex.Message }));
            }
        }
        return 0;
    }
}
