// B.CsHost: a C# assembly as a relative of B. Reads public static methods by reflection
// and invokes them across JSON lines. Usage: B.CsHost --describe <dll> | B.CsHost <dll>
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;

static class Program
{
    static readonly JsonSerializerOptions Json = new() { IncludeFields = true };

    static string? BType(Type t)
    {
        var u = Nullable.GetUnderlyingType(t);
        if (u != null) { var inner = BType(u); return inner == null ? null : $"Option[{inner}]"; }
        if (t == typeof(int) || t == typeof(long) || t == typeof(short) || t == typeof(byte)) return "Int";
        if (t == typeof(double) || t == typeof(float) || t == typeof(decimal)) return "Float";
        if (t == typeof(string)) return "Text";
        if (t == typeof(bool)) return "Bool";
        if (t.IsArray && t.GetArrayRank() == 1) { var e = BType(t.GetElementType()!); return e == null ? null : $"List[{e}]"; }
        if (t.IsGenericType)
        {
            var def = t.GetGenericTypeDefinition();
            var a = t.GetGenericArguments();
            if (def == typeof(List<>) || def == typeof(IReadOnlyList<>) || def == typeof(IList<>) || def == typeof(IEnumerable<>))
            { var e = BType(a[0]); return e == null ? null : $"List[{e}]"; }
            if ((def == typeof(Dictionary<,>) || def == typeof(IReadOnlyDictionary<,>) || def == typeof(IDictionary<,>)) && a[0] == typeof(string))
            { var v = BType(a[1]); return v == null ? null : $"Dict[Text, {v}]"; }
        }
        return null;
    }

    static IEnumerable<(Type type, MethodInfo method)> Methods(Assembly asm)
    {
        foreach (var type in asm.GetExportedTypes().Where(t => t.IsClass && t.IsAbstract && t.IsSealed).OrderBy(t => t.Name))
        {
            var all = type.GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly)
                .Where(m => !m.IsSpecialName && !m.IsGenericMethod).ToList();
            foreach (var m in all.Where(m => all.Count(o => o.Name == m.Name) == 1).OrderBy(m => m.Name))
                yield return (type, m);
        }
    }

    static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--describe")
        {
            var asm = Assembly.LoadFrom(args[1]);
            var outList = new JsonArray();
            foreach (var (type, m) in Methods(asm))
            {
                var ps = m.GetParameters().Select(p => BType(p.ParameterType)).ToList();
                var r = m.ReturnType == typeof(void) ? null : BType(m.ReturnType);
                if (r == null || ps.Any(p => p == null) || m.GetParameters().Any(p => p.IsOut || p.ParameterType.IsByRef)) continue;
                outList.Add(new JsonObject { ["type"] = type.Name, ["name"] = m.Name, ["params"] = new JsonArray(ps.Select(p => (JsonNode)p!).ToArray()), ["result"] = r });
            }
            Console.WriteLine(new JsonObject { ["functions"] = outList }.ToJsonString());
            return 0;
        }
        if (args.Length != 1) { Console.Error.WriteLine("usage: B.CsHost [--describe] <dll>"); return 2; }
        var assembly = Assembly.LoadFrom(args[0]);
        var table = Methods(assembly).ToDictionary(x => x.type.Name + "." + x.method.Name, x => x.method);
        string? line;
        while ((line = Console.ReadLine()) is not null)
        {
            JsonObject reply;
            try
            {
                var q = JsonNode.Parse(line)!.AsObject();
                var key = q["type"]!.GetValue<string>() + "." + q["method"]!.GetValue<string>();
                if (!table.TryGetValue(key, out var m)) throw new InvalidOperationException("unknown method " + key);
                var ps = m.GetParameters();
                var a = q["args"]!.AsArray();
                if (a.Count != ps.Length) throw new ArgumentException($"{key} expects {ps.Length} arguments");
                var values = ps.Select((p, i) => a[i] == null ? null : a[i]!.Deserialize(p.ParameterType, Json)).ToArray();
                object? result;
                try { result = m.Invoke(null, values); }
                catch (TargetInvocationException e) when (e.InnerException != null) { throw e.InnerException; }
                reply = new JsonObject { ["ok"] = true, ["value"] = JsonSerializer.SerializeToNode(result, Json) };
            }
            catch (Exception e)
            {
                reply = new JsonObject { ["ok"] = false, ["error"] = e.GetType().Name + ": " + e.Message };
            }
            Console.WriteLine(reply.ToJsonString());
        }
        return 0;
    }
}
