using System.Text.Json;
using Packaging;
using Reorder;

const int Window = 28;
const double MinOrderValue = 500.0;

var input = await Console.In.ReadToEndAsync();
using var doc = JsonDocument.Parse(input);
var root = doc.RootElement;

var today = Dates.Parse(root.GetProperty("today").GetString()!);
var windowStart = today.DayNumber - Window;
var week = Dates.IsoWeek(today);
var season = week >= 48 && week <= 52;

// Daily quantities per sku over the 28 days before today (oldest first).
var series = new Dictionary<string, double[]>(StringComparer.Ordinal);
if (root.TryGetProperty("sales", out var sales))
{
    foreach (var s in sales.EnumerateArray())
    {
        var sku = s.GetProperty("sku").GetString()!;
        var day = Dates.Parse(s.GetProperty("date").GetString()!).DayNumber;
        var idx = day - windowStart;
        if (idx < 0 || idx >= Window) continue;
        if (!series.TryGetValue(sku, out var arr))
            series[sku] = arr = new double[Window];
        arr[idx] += s.GetProperty("qty").GetInt32();
    }
}

var orders = new List<(string Sku, int Qty, string Arrive)>();
var unknown = new List<string>();

foreach (var item in root.GetProperty("items").EnumerateArray())
{
    var sku = item.GetProperty("sku").GetString()!;
    var supplier = item.GetProperty("supplier").GetString()!;
    var stock = item.GetProperty("stock").GetInt32();
    var pack = item.GetProperty("pack").GetInt32();

    var resolved = Leadtime.Resolve(supplier);
    if (resolved is null || !Leadtime.TryDays(resolved, out var lead))
    {
        unknown.Add(sku);
        continue;
    }

    var daily = series.TryGetValue(sku, out var s) ? s : new double[Window];
    var forecast = Stats.TrailingMean(daily, 7);
    if (season) forecast *= 1.25;
    var safety = Stats.Percentile(daily, 90);
    var need = forecast * (lead + 7) + safety - stock;

    if (need > 0)
    {
        var qty = Packs.RoundUp((int)Math.Ceiling(need), pack);
        var price = item.GetProperty("price").GetDouble();
        if (qty * price < MinOrderValue) continue;
        orders.Add((sku, qty, Dates.ToWeekday(Dates.AddDays(today.ToString(Dates.Format), lead))));
    }
}

unknown.Sort(StringComparer.Ordinal);

using var stream = new MemoryStream();
using (var w = new Utf8JsonWriter(stream))
{
    w.WriteStartObject();
    w.WriteStartObject("orders");
    foreach (var o in orders)
    {
        w.WriteStartObject(o.Sku);
        w.WriteNumber("qty", o.Qty);
        w.WriteString("arrive", o.Arrive);
        w.WriteEndObject();
    }
    w.WriteEndObject();
    w.WriteStartArray("unknown");
    foreach (var u in unknown) w.WriteStringValue(u);
    w.WriteEndArray();
    w.WriteEndObject();
}
Console.Out.Write(System.Text.Encoding.UTF8.GetString(stream.ToArray()) + "\n");
