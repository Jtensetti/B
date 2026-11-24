# Driver: reads a JSON array of [gross, table] pairs on stdin and prints withholding() for each.
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "libs", "payroll"))
from withholding import withholding  # noqa: E402

out = []
for gross, table in json.load(sys.stdin):
    try:
        out.append({"ok": True, "value": withholding(gross, table), "error": None})
    except Exception as e:  # report library errors per item
        out.append({"ok": False, "value": 0, "error": str(e)})
print(json.dumps(out))
