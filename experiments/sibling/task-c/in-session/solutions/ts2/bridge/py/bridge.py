"""Reads one request per line from stdin and prints one answer per line.

  add DATE DAYS    -> add_days(DATE, DAYS)
  week DATE        -> iso_week(DATE)
  arrive DATE DAYS -> to_weekday(add_days(DATE, DAYS))
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "libs", "weeks"))

from dates import add_days, iso_week, to_weekday  # noqa: E402

for line in sys.stdin:
    parts = line.split()
    if not parts:
        continue
    if parts[0] == "add":
        print(add_days(parts[1], int(parts[2])))
    elif parts[0] == "arrive":
        print(to_weekday(add_days(parts[1], int(parts[2]))))
    elif parts[0] == "week":
        print(iso_week(parts[1]))
