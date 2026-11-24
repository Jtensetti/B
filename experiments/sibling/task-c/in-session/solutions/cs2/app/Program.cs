using System.Text.Json;
using System.Text.Json.Serialization;
using App;
using Packaging;

var stdin = Console.OpenStandardInput();
using var reader = new StreamReader(stdin);
using var doc = JsonDocument.Parse(reader.ReadToEnd());
var root = doc.RootElement;

const int Window = 28;
var today = Dates.Parse(root.GetProperty("today").GetString()!);
var windowStart = today.AddDays(-Window);

// Daily sales per sku over the 28 days before today (oldest first).
var series = new Dictionary<string, double[]>(StringComparer.Ordinal);
foreach (var sale in root.GetProperty("sales").EnumerateArray())
{
    var sku = sale.GetProperty("sku").GetString()!;
    var date = Dates.Parse(sale.GetProperty("date").GetString()!);
    int offset = date.DayNumber - windowStart.DayNumber;
    if (offset < 0 || offset >= Window) continue;
    if (!series.TryGetValue(sku, out var daily))
    {
        daily = new double[Window];
        series[sku] = daily;
    }
    daily[offset] += sale.GetProperty("qty").GetInt32();
}

bool season = Dates.IsoWeek(today) is >= 48 and <= 52;

var orders = new SortedDictionary<string, Order>(StringComparer.Ordinal);
var unknown = new SortedSet<string>(StringComparer.Ordinal);

foreach (var item in root.GetProperty("items").EnumerateArray())
{
    var sku = item.GetProperty("sku").GetString()!;
    var supplier = item.GetProperty("supplier").GetString()!;
    int stock = item.GetProperty("stock").GetInt32();
    int pack = item.GetProperty("pack").GetInt32();
    decimal price = item.GetProperty("price").GetDecimal();

    if (!Leadtime.TryDays(supplier, out int lead))
    {
        // Misspelled supplier: nearest known name within distance 2 (ties: alphabetical).
        string? best = null;
        int bestDist = int.MaxValue;
        foreach (var name in Leadtime.Suppliers().OrderBy(n => n, StringComparer.Ordinal))
        {
            int d = Edit.Distance(supplier, name);
            if (d < bestDist) { bestDist = d; best = name; }
        }
        if (best is null || bestDist > 2 || !Leadtime.TryDays(best, out lead))
        {
            unknown.Add(sku);
            continue;
        }
    }

    var daily = series.TryGetValue(sku, out var s) ? s : new double[Window];
    double forecast = Stats.TrailingMean(daily, 7);
    if (season) forecast *= 1.25;
    double safety = Stats.Percentile(daily, 90);
    double need = forecast * (lead + 7) + safety - stock;

    if (need > 0)
    {
        int whole = (int)Math.Ceiling(need);
        int qty = Packs.RoundUp(whole, pack);
        // Orders worth less than 500 SEK are not placed.
        if (qty * price >= 500m)
            orders[sku] = new Order(qty, Dates.Format1(Dates.ToWeekday(today.AddDays(lead))));
    }
}

var output = new Result(orders, unknown.ToList());
Console.WriteLine(JsonSerializer.Serialize(output));

record Order(
    [property: JsonPropertyName("qty")] int Qty,
    [property: JsonPropertyName("arrive")] string Arrive);

record Result(
    [property: JsonPropertyName("orders")] SortedDictionary<string, Order> Orders,
    [property: JsonPropertyName("unknown")] List<string> Unknown);
