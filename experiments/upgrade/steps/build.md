# Build

Quote parcel shipping for a furniture shop.

Read one line of JSON from standard input:
{"orders": [{"id": "<text>", "product": "<text>", "country": "<ISO code>", "express": <bool, optional>}, ...], "catalog": {"<product name>": <weight in kg>, ...}}

Write one line of JSON: {"quotes": {"<id>": <price in SEK incl. VAT>, ...}, "unknown": [<ids>, sorted]}.

- Product names are often misspelled. Use the catalog name with the smallest Levenshtein distance, if that distance is at most 2. Ties go to the alphabetically first name. Otherwise the order is unknown. The npm package fastest-levenshtein is installed in your workspace (node_modules).
- The tariff comes from the Python library `tariff` (tariff.py in your workspace; its CHANGELOG.md is next to it). `tariff.zone(country)` gives the zone and raises KeyError for countries the carrier does not serve; such orders are unknown. `tariff.base_price(zone, weight_kg)` gives the carrier's price.
- The customer pays the carrier's price excluding VAT, plus 50 kr for express, plus 25 % VAT on the sum. Round the quote to 2 decimals.
- tariff is maintained by another team. A bot upgrades it in your workspace from time to time.
