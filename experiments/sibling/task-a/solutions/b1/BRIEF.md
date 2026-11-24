# Build

Delivery quotes for a furniture shop in Stockholm.

Your workspace has five libraries in `libs/`, each maintained by another team in its own language:
- `libs/tariff` (Go module): `Zone(country) (int, error)` gives the carrier's zone and an error for countries it does not serve; `BasePrice(zone, weightKg) float64` gives the carrier price in SEK excluding VAT.
- `libs/geo` (Rust crate): `road_km(lat1, lon1, lat2, lon2) -> f64` estimates the road distance.
- `libs/Tax` (C# project): `Vat.Rate(country)` gives the VAT rate; `Vat.ReverseCharge(country, business)` says whether a business customer pays no VAT.
- `libs/calendar` (Python module `workdays.py`): `next_workday(iso_date)` gives the first Swedish working day strictly after a date; `is_workday(iso_date)`.
- `node_modules/fastest-levenshtein` (npm package): `distance(a, b)` and `closest(name, names)`.

Read one line of JSON from standard input:
{"depot": {"lat": <float>, "lon": <float>}, "catalog": {"<product>": <weight in kg>}, "orders": [{"id": "<text>", "product": "<text>", "country": "<ISO code>", "lat": <float>, "lon": <float>, "date": "YYYY-MM-DD", "business": <bool>}, ...]}

Write one line of JSON: {"quotes": {"<id>": {"price": <SEK including VAT>, "delivery": "YYYY-MM-DD"}, ...}, "unknown": [<ids, sorted>]}

Rules:
- The product is the catalog name with the smallest Levenshtein distance to the ordered name, if that distance is at most 2. Ties go to the alphabetically first name. Otherwise the order is unknown.
- An order to a country the carrier does not serve is unknown.
- net = BasePrice(zone, weight) + 0.80 SEK for every road kilometre beyond 300 km from the depot to the customer.
- VAT is Vat.Rate(country) on net, or 0 when Vat.ReverseCharge(country, business) is true.
- price = net × (1 + VAT), rounded to 2 decimals.
- delivery = next_workday(order date).

The behaviour of each library is defined by its code in `libs/`.
