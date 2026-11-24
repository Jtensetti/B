# Reads a JSON array of {"date": ISO date, "express": bool} on stdin and writes a JSON
# array of delivery dates using libs/calendar/workdays.py. An express order is delivered on
# its own date when that is a working day, otherwise on the next working day.
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "libs", "calendar"))
from workdays import is_workday, next_workday  # noqa: E402

requests = json.load(sys.stdin)
days = []
for r in requests:
    if r["express"] and is_workday(r["date"]):
        days.append(r["date"])
    else:
        days.append(next_workday(r["date"]))
json.dump(days, sys.stdout)
