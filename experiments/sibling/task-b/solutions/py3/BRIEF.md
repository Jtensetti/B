# Build

Monthly payslips for a staffing company.

Your workspace has five libraries, each maintained by another team in its own language:
- `libs/hours` (Go module): `Parse(text) (float64, error)` reads a duration written as H:MM and returns hours, or an error.
- `libs/quarter` (Rust crate): `round_up(hours) -> f64` rounds hours up to the next quarter hour.
- `libs/Rules` (C# project): `Overtime.Multiplier(weekday)` for "Mon".."Sun", and `Overtime.Holiday()`.
- `libs/payroll` (Python module `withholding.py`): `withholding(gross, table) -> int`, the tax to withhold in whole kronor.
- `node_modules/semver` (npm package): semantic-version comparisons such as `satisfies(version, range)`.

Read one line of JSON from standard input:
{"month": "YYYY-MM", "employees": [{"id": "<text>", "hourly": <SEK>, "table": <int>, "contract": "<semver>"}, ...], "shifts": [{"id": "<text>", "employee": "<employee id>", "date": "YYYY-MM-DD", "hours": "H:MM"}, ...]}

Write one line of JSON: {"payslips": {"<employee id>": {"hours": <number>, "gross": <SEK>, "tax": <SEK>, "net": <SEK>}, ...}, "rejected": [<shift ids, sorted>]}

Rules:
- A shift is rejected when its employee is unknown or its hours cannot be parsed by `Parse`.
- A shift's hours are `round_up(Parse(hours))`.
- A shift pays hours × the employee's hourly rate × `Multiplier(weekday of the date)`.
- Every employee gets a payslip. hours is the sum of the employee's shift hours. gross is the sum of the shift pay, rounded to 2 decimals. tax = `withholding(gross, table)`. net = gross − tax.

The behaviour of each library is defined by its code.
