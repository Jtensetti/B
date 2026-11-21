// B .NET v0.2: explicit signatures, guarded JSON-lines values, no arbitrary reflection.
using System.Text.Json;
using System.Text.RegularExpressions;

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
                void Arity(int n)
                {
                    if (args.Length != n) throw new ArgumentException($"Expected {n} arguments");
                }
                double Number(int n)
                {
                    if (n >= args.Length || args[n].ValueKind != JsonValueKind.Number)
                        throw new ArgumentException($"Argument {n + 1} must be numeric");
                    double value = args[n].GetDouble();
                    if (!double.IsFinite(value)) throw new ArgumentException("Non-finite numbers are not supported");
                    return value;
                }
                string Text(int n)
                {
                    if (n >= args.Length || args[n].ValueKind != JsonValueKind.String)
                        throw new ArgumentException($"Argument {n + 1} must be a string");
                    return args[n].GetString()!;
                }
                object result;
                if (type == "System.Math")
                {
                    result = method switch
                    {
                        "Sqrt" when args.Length == 1 => Math.Sqrt(Number(0)),
                        "Pow" when args.Length == 2 => Math.Pow(Number(0), Number(1)),
                        "Abs" when args.Length == 1 => Math.Abs(Number(0)),
                        "Min" when args.Length == 2 => Math.Min(Number(0), Number(1)),
                        "Max" when args.Length == 2 => Math.Max(Number(0), Number(1)),
                        _ => throw new InvalidOperationException("Method not allowlisted or wrong arity")
                    };
                    if (!double.IsFinite((double)result))
                        throw new ArithmeticException("Non-finite output rejected");
                }
                else if (type == "System.Text.RegularExpressions.Regex" && method == "IsMatch")
                {
                    Arity(2);
                    // Bound the matching time; imported regexes are not a trusted computation.
                    result = Regex.IsMatch(Text(0), Text(1), RegexOptions.None, TimeSpan.FromMilliseconds(250));
                }
                else throw new InvalidOperationException("Type or method not allowlisted");
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
