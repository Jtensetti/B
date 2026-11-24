# Build

Monthly invoices for a subscription service.

Read one line of JSON from standard input:
{"month": "YYYY-MM", "rates": {"EUR": <SEK per EUR>, "NOK": <SEK per NOK>}, "plans": {"<name>": {"price": <SEK per month>}}, "customers": [{"id": "<text>", "country": "SE"|"NO"|"DE"|"FR", "plan": "<name>", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" or null, "app_version": "<semver>"}, ...]}

Write one line of JSON: {"invoices": {"<customer id>": {"currency": "SEK"|"NOK"|"EUR", "net": <number>, "vat": <number>, "total": <number>}, ...}}

Rules:
- A customer is active on every day from `start` to `end`, both included. `end: null` means still active.
- Billable days are the customer's active days within the month. A customer with no billable day in the month gets no invoice.
- The SEK amount is the plan price times billable days divided by the number of days in the month.
- Currency by country: SE pays SEK, NO pays NOK, DE and FR pay EUR. Convert from SEK by dividing by the rate (SEK per unit).
- VAT by country: SE 25 %, NO 25 %, DE 19 %, FR 20 %.
- net is the converted amount rounded to 2 decimals. vat is net times the VAT rate, rounded to 2 decimals. total is net plus vat.

Example: plan price 300 SEK, a SE customer active on 10 of March's 31 days: net 96.77, vat 24.19, total 120.96.
