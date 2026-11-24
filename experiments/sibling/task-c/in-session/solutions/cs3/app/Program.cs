using System.Globalization;
using System.Text;
using System.Text.Json;
using App;
using Packaging;

var input = Console.In.ReadToEnd();
using var doc = JsonDocument.Parse(input);
var root = doc.RootElement;

string today = root.GetProperty("today").GetString()!;
DateOnly todayDate = Dates.Parse(today);

// Sales grouped by sku and by day offset from today (0 = oldest of the 28-day window).
var sales = new Dictionary<string, Dictionary<DateOnly, long>>(StringComparer.Ordinal);
if (root.TryGetProperty("sales", out var salesEl))
{
    foreach (var s in salesEl.EnumerateArray())
    {
        string sku = s.GetProperty("sku").GetString()!;
        DateOnly date = Dates.Parse(s.GetProperty("date").GetString()!);
        long qty = s.GetProperty("qty").GetInt64();
        if (!sales.TryGetValue(sku, out var byDay))
        {
            byDay = new Dictionary<DateOnly, long>();
            sales[sku] = byDay;
        }
        byDay[date] = byDay.TryGetValue(date, out var cur) ? cur + qty : qty;
    }
}

var orders = new List<(string Sku, int Qty, string Arrive)>();
var unknown = new List<string>();

foreach (var item in root.GetProperty("items").EnumerateArray())
{
    string sku = item.GetProperty("sku").GetString()!;
    string supplier = LeadTime.Match(item.GetProperty("supplier").GetString()!) ?? "";
    long stock = item.GetProperty("stock").GetInt64();
    int pack = item.GetProperty("pack").GetInt32();
    decimal price = item.GetProperty("price").GetDecimal();

    if (!LeadTime.TryDays(supplier, out int lead))
    {
        unknown.Add(sku);
        continue;
    }

    // Window: today - 28 ... today - 1, oldest first.
    var series = new double[28];
    sales.TryGetValue(sku, out var byDay);
    for (int i = 0; i < 28; i++)
    {
        var day = todayDate.AddDays(i - 28);
        if (byDay != null && byDay.TryGetValue(day, out var q)) series[i] = q;
    }

    // Forecast: mean of the last 7 days of the series.
    double forecast = Stats.TrailingMean(series, 7);
    // Season: ISO weeks 48 to 52 of today scale the forecast by 1.25.
    int week = ISOWeek.GetWeekOfYear(todayDate.ToDateTime(TimeOnly.MinValue));
    if (week >= 48 && week <= 52) forecast *= 1.25;
    double safety = Stats.Percentile(series, 90);
    double need = forecast * (lead + 7) + safety - stock;

    if (need > 0)
    {
        long whole = (long)Math.Ceiling(need);
        int qty = Packs.RoundUp((int)whole, pack);
        // Orders worth less than 500 SEK are not placed (the item is still known).
        if (qty * price >= 500m)
            orders.Add((sku, qty, Dates.ToWeekday(Dates.AddDays(today, lead))));
    }
}

unknown.Sort(CompareCodePoints);

var sb = new StringBuilder();
sb.Append("{\"orders\":{");
for (int i = 0; i < orders.Count; i++)
{
    if (i > 0) sb.Append(',');
    sb.Append(JsonSerializer.Serialize(orders[i].Sku)).Append(":{\"qty\":").Append(orders[i].Qty)
      .Append(",\"arrive\":").Append(JsonSerializer.Serialize(orders[i].Arrive)).Append('}');
}
sb.Append("},\"unknown\":[");
for (int i = 0; i < unknown.Count; i++)
{
    if (i > 0) sb.Append(',');
    sb.Append(JsonSerializer.Serialize(unknown[i]));
}
sb.Append("]}");
Console.Out.Write(sb.ToString() + "\n");

static int CompareCodePoints(string a, string b)
{
    var ra = a.EnumerateRunes().GetEnumerator();
    var rb = b.EnumerateRunes().GetEnumerator();
    while (true)
    {
        bool ha = ra.MoveNext(), hb = rb.MoveNext();
        if (!ha || !hb) return ha == hb ? 0 : (ha ? 1 : -1);
        int c = ra.Current.Value.CompareTo(rb.Current.Value);
        if (c != 0) return c;
    }
}
