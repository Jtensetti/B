# Build

Reorder suggestions for a furniture warehouse.

Your workspace has five libraries, each maintained by another team in its own language:
- `libs/leadtime` (Go module): `Days(supplier) (int, error)` is the delivery time in days, or an error for an unknown supplier; `Suppliers() []string` lists the known suppliers.
- `libs/stats` (Rust crate): `mean(values)`, `percentile(values, p)` and `trailing_mean(values, window)`.
- `libs/Packaging` (C# project): `Packs.RoundUp(quantity, packSize)` rounds a quantity up to whole packs.
- `libs/weeks` (Python module `dates.py`): `add_days(iso_date, days)`, `iso_week(iso_date)` and `to_weekday(iso_date)`.
- `node_modules/fastest-levenshtein` (npm package): `distance(a, b)` and `closest(name, names)`.

Read one line of JSON from standard input:
{"today": "YYYY-MM-DD", "items": [{"sku": "<text>", "supplier": "<text>", "stock": <int>, "pack": <int>}, ...], "sales": [{"sku": "<text>", "date": "YYYY-MM-DD", "qty": <int>}, ...]}

Write one line of JSON: {"orders": {"<sku>": {"qty": <int>, "arrive": "YYYY-MM-DD"}, ...}, "unknown": [<skus, sorted>]}

Rules:
- An item's daily series has 28 numbers: the quantity sold on each of the 28 days before today, oldest first (today − 28 to today − 1), 0 on days without sales. Several sales on one day add up. Other sales are ignored.
- An item whose supplier makes `Days` fail is unknown.
- forecast = mean(series). safety = percentile(series, 90). lead = Days(supplier).
- need = forecast × (lead + 7) + safety − stock.
- When need > 0, the item is ordered: qty = RoundUp(need rounded up to a whole number, pack), and arrive = add_days(today, lead). Otherwise it gets no order.

The behaviour of each library is defined by its code.
