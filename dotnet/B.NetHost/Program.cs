// B .NET host: explicit signatures, guarded JSON-lines values, no arbitrary reflection.
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Reflection;

static class Program
{
    static int Main(string[] cliArgs)
    {
        if (cliArgs.Length == 1 && cliArgs[0] == "--describe")
        {
            // Reflect the exact overloads the transport can invoke. This is
            // metadata discovery, not permission to call arbitrary .NET APIs.
            var permitted = new Dictionary<string, string[]>
            {
                ["System.Math"] = new[] { "Abs", "Ceiling", "Floor", "Max", "Min", "Pow", "Round", "Sqrt" },
                ["System.Text.RegularExpressions.Regex"] = new[] { "IsMatch", "Replace" },
                ["System.Uri"] = new[] { "EscapeDataString", "UnescapeDataString" }
            };
            var types = new SortedDictionary<string, object>();
            foreach (var (typeName, names) in permitted)
            {
                Type type = typeName switch
                {
                    "System.Math" => typeof(Math),
                    "System.Text.RegularExpressions.Regex" => typeof(Regex),
                    "System.Uri" => typeof(Uri),
                    _ => throw new InvalidOperationException("Unexpected type")
                };
                var methods = type.GetMethods(BindingFlags.Static | BindingFlags.Public)
                    .Where(m => names.Contains(m.Name))
                    .Where(m => typeName switch
                    {
                        "System.Math" => m.GetParameters().All(p => p.ParameterType == typeof(double))
                            && m.ReturnType == typeof(double)
                            && (m.Name is "Abs" or "Ceiling" or "Floor" or "Round" or "Sqrt"
                                ? m.GetParameters().Length == 1
                                : m.GetParameters().Length == 2),
                        "System.Text.RegularExpressions.Regex" =>
                            (m.Name == "IsMatch" && m.GetParameters().Length == 2
                                && m.GetParameters().All(p => p.ParameterType == typeof(string))
                                && m.ReturnType == typeof(bool))
                            || (m.Name == "Replace" && m.GetParameters().Length == 3
                                && m.GetParameters().All(p => p.ParameterType == typeof(string))
                                && m.ReturnType == typeof(string)),
                        "System.Uri" => m.GetParameters().Length == 1
                            && m.GetParameters()[0].ParameterType == typeof(string)
                            && m.ReturnType == typeof(string),
                        _ => false
                    })
                    .OrderBy(m => m.Name, StringComparer.Ordinal)
                    .Select(m => new
                    {
                        name = m.Name,
                        @params = m.GetParameters().Select(p => p.ParameterType == typeof(double) ? "Float" : "Text").ToArray(),
                        result = m.ReturnType == typeof(double) ? "Float" : (m.ReturnType == typeof(bool) ? "Bool" : "Text")
                    })
                    .ToArray();
                types[typeName] = methods;
            }
            Console.WriteLine(JsonSerializer.Serialize(new { schema = 1, runtime = "B.NetHost/.NET10", types }));
            return 0;
        }
        if (cliArgs.Length != 0) { Console.Error.WriteLine("Unknown option"); return 2; }

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
                        "Round" when args.Length == 1 => Math.Round(Number(0)),
                        "Floor" when args.Length == 1 => Math.Floor(Number(0)),
                        "Ceiling" when args.Length == 1 => Math.Ceiling(Number(0)),
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
                else if (type == "System.Text.RegularExpressions.Regex" && method == "Replace")
                {
                    Arity(3);
                    result = Regex.Replace(Text(0), Text(1), Text(2), RegexOptions.None, TimeSpan.FromMilliseconds(250));
                }
                else if (type == "System.Uri" && method == "EscapeDataString")
                {
                    Arity(1);
                    result = Uri.EscapeDataString(Text(0));
                }
                else if (type == "System.Uri" && method == "UnescapeDataString")
                {
                    Arity(1);
                    result = Uri.UnescapeDataString(Text(0));
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
