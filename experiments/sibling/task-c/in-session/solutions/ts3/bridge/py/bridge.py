"""Bridge to libs/weeks. Reads {"requests":[...]} on stdin and writes {"results":[...]} on stdout.

Each request is {"op":"add_days","date":"YYYY-MM-DD","days":n}, {"op":"iso_week","date":...}
or {"op":"to_weekday","date":...}. Results are in request order.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "libs", "weeks"))

import dates  # noqa: E402


def run(req):
    op = req["op"]
    if op == "add_days":
        return dates.add_days(req["date"], req["days"])
    if op == "iso_week":
        return dates.iso_week(req["date"])
    if op == "to_weekday":
        return dates.to_weekday(req["date"])
    raise ValueError("unknown op " + op)


payload = json.load(sys.stdin)
json.dump({"results": [run(r) for r in payload["requests"]]}, sys.stdout)
sys.stdout.write("\n")
