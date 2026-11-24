using System.Text;
using System.Text.Json;
using App;
using Tax;

var input = Console.In.ReadToEnd();
using var doc = JsonDocument.Parse(input);
var root = doc.RootElement;

var depot = root.GetProperty("depot");
double depotLat = depot.GetProperty("lat").GetDouble();
double depotLon = depot.GetProperty("lon").GetDouble();

// Catalog sorted by name so ties in Levenshtein distance go to the alphabetically first name.
var catalog = root.GetProperty("catalog").EnumerateObject()
    .Select(p => (Name: p.Name, Weight: p.Value.GetDouble()))
    .OrderBy(c => c.Name, StringComparer.Ordinal)
    .ToList();

// SEK per EUR, used for orders to countries other than Sweden.
double eurRate = root.TryGetProperty("rates", out var ratesEl) && ratesEl.TryGetProperty("EUR", out var eurEl)
    ? eurEl.GetDouble() : 0.0;

var quotes = new SortedDictionary<string, (double Price, string Currency, string Delivery)>(StringComparer.Ordinal);
var unknown = new List<string>();

foreach (var o in root.GetProperty("orders").EnumerateArray())
{
    string id = o.GetProperty("id").GetString()!;
    string product = o.GetProperty("product").GetString()!;
    string country = o.GetProperty("country").GetString()!;
    double lat = o.GetProperty("lat").GetDouble();
    double lon = o.GetProperty("lon").GetDouble();
    string date = o.GetProperty("date").GetString()!;
    bool business = o.GetProperty("business").GetBoolean();
    int qty = o.TryGetProperty("qty", out var qEl) && qEl.ValueKind == JsonValueKind.Number ? qEl.GetInt32() : 1;
    bool express = o.TryGetProperty("express", out var eEl) && eEl.ValueKind == JsonValueKind.True;

    // Product match: nearest catalog name within distance 2.
    (string Name, double Weight)? match = null;
    int bestDist = int.MaxValue;
    foreach (var c in catalog)
    {
        int d = Levenshtein.Distance(product, c.Name);
        if (d < bestDist) { bestDist = d; match = c; }
    }
    if (match is null || bestDist > 2 || !Tariff.TryZone(country, out int zone))
    {
        unknown.Add(id);
        continue;
    }

    double km = Geo.RoadKm(depotLat, depotLon, lat, lon);
    double weightKg = qty * match.Value.Weight;
    // Free freight: business parcels of 50 kg or more carry no base price.
    bool freeFreight = business && weightKg >= 50.0;
    double basePrice = freeFreight ? 0.0 : Tariff.BasePrice(zone, weightKg);
    if (express) basePrice *= 1.5;
    double surcharge = Math.Min(400.0, km > 300 ? (km - 300) * 0.80 : 0.0);
    double net = basePrice + surcharge;

    double vatRate = Vat.ReverseCharge(country, business) ? 0.0 : Vat.Rate(country);
    double priceSek = net * (1 + vatRate);
    bool isSweden = country.Trim().Equals("SE", StringComparison.OrdinalIgnoreCase);
    string currency = isSweden ? "SEK" : "EUR";
    double price = Math.Round(isSweden ? priceSek : priceSek / eurRate, 2, MidpointRounding.AwayFromZero);

    string delivery = express && Workdays.IsWorkday(date) ? date : Workdays.NextWorkday(date);
    quotes[id] = (price, currency, delivery);
}

unknown.Sort(StringComparer.Ordinal);

using var ms = new MemoryStream();
using (var w = new Utf8JsonWriter(ms))
{
    w.WriteStartObject();
    w.WritePropertyName("quotes");
    w.WriteStartObject();
    foreach (var (id, q) in quotes)
    {
        w.WritePropertyName(id);
        w.WriteStartObject();
        w.WriteNumber("price", q.Price);
        w.WriteString("currency", q.Currency);
        w.WriteString("delivery", q.Delivery);
        w.WriteEndObject();
    }
    w.WriteEndObject();
    w.WritePropertyName("unknown");
    w.WriteStartArray();
    foreach (var id in unknown) w.WriteStringValue(id);
    w.WriteEndArray();
    w.WriteEndObject();
}
var stdout = Console.OpenStandardOutput();
ms.WriteTo(stdout);
stdout.Write(Encoding.UTF8.GetBytes("\n"));
stdout.Flush();
