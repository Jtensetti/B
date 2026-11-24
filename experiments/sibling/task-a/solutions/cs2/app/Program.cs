using System.Text.Json;
using System.Text;
using Tax;
using App;

var stdin = Console.In.ReadToEnd();
using var doc = JsonDocument.Parse(stdin);
var root = doc.RootElement;

double depotLat = root.GetProperty("depot").GetProperty("lat").GetDouble();
double depotLon = root.GetProperty("depot").GetProperty("lon").GetDouble();

// Catalog names sorted ordinally so that ties go to the alphabetically first name.
var catalog = root.GetProperty("catalog").EnumerateObject()
    .Select(p => (Name: p.Name, Weight: p.Value.GetDouble()))
    .OrderBy(c => c.Name, StringComparer.Ordinal)
    .ToList();

// SEK per EUR, used for orders to countries other than SE.
double eurRate = root.TryGetProperty("rates", out var rates) && rates.TryGetProperty("EUR", out var eur)
    ? eur.GetDouble() : double.NaN;

var quotes = new SortedDictionary<string, (double Price, string Delivery, string Currency)>(StringComparer.Ordinal);
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
    // Optional quantity (default 1): the parcel weighs qty times the catalog weight.
    double qty = o.TryGetProperty("qty", out var qe) && qe.ValueKind == JsonValueKind.Number ? qe.GetDouble() : 1.0;
    // Optional express flag (default false): base price x1.5, and same-day delivery on a working day.
    bool express = o.TryGetProperty("express", out var ex) && ex.ValueKind == JsonValueKind.True;

    // Product: nearest catalog name, if within distance 2.
    (string Name, double Weight)? match = null;
    int best = int.MaxValue;
    foreach (var c in catalog)
    {
        int d = Lev.Distance(product, c.Name);
        if (d < best) { best = d; match = c; }
    }
    if (match is null || best > 2 || !Tariff.TryZone(country, out int zone))
    {
        unknown.Add(id);
        continue;
    }

    double roadKm = Geo.RoadKm(depotLat, depotLon, lat, lon);
    // Free freight: business parcels of 50 kg or more have no base price (distance surcharge still applies).
    double parcelKg = qty * match.Value.Weight;
    double basePrice = business && parcelKg >= 50 ? 0.0 : Tariff.BasePrice(zone, parcelKg);
    if (express) basePrice *= 1.5;
    // Distance surcharge: 0.80 SEK per road km beyond 300 km, capped at 400 SEK per order.
    double surcharge = Math.Min(400.0, 0.80 * Math.Max(0, roadKm - 300));
    double net = basePrice + surcharge;

    double vat = Vat.ReverseCharge(country, business) ? 0.0 : Vat.Rate(country);
    double price = Math.Round(net * (1 + vat), 2, MidpointRounding.AwayFromZero);

    string delivery = express && Calendar.IsWorkday(date)
        ? date
        : Calendar.NextWorkday(date);
    // Customers outside Sweden pay in euros: SEK price divided by the SEK-per-EUR rate.
    bool sweden = country.Trim().ToUpperInvariant() == "SE";
    if (sweden)
    {
        quotes[id] = (price, delivery, "SEK");
    }
    else
    {
        double eurPrice = Math.Round(price / eurRate, 2, MidpointRounding.AwayFromZero);
        quotes[id] = (eurPrice, delivery, "EUR");
    }
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
        w.WriteString("delivery", q.Delivery);
        w.WriteString("currency", q.Currency);
        w.WriteEndObject();
    }
    w.WriteEndObject();
    w.WritePropertyName("unknown");
    w.WriteStartArray();
    foreach (var id in unknown) w.WriteStringValue(id);
    w.WriteEndArray();
    w.WriteEndObject();
}
Console.Out.Write(Encoding.UTF8.GetString(ms.ToArray()) + "\n");
