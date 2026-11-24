import sys, json, datetime
sys.path.insert(0, "/tmp/claude-0/-home-user-B/bc1bd2a3-1ba0-5a86-9b4b-8c9b2f90e18b/scratchpad/sibA/rs3/libs/calendar")
from workdays import next_workday
start = datetime.date(2025, 1, 1)
dates = [(start + datetime.timedelta(days=i)).isoformat() for i in range(0, 900)]
orders = [{"id": d, "product": "A", "country": "SE", "lat": 59.3, "lon": 18.0, "date": d, "business": False} for d in dates]
inp = {"depot": {"lat": 59.3, "lon": 18.0}, "catalog": {"A": 1.0}, "orders": orders}
json.dump(inp, open("/tmp/claude-0/-home-user-B/bc1bd2a3-1ba0-5a86-9b4b-8c9b2f90e18b/scratchpad/sibA/rs3/check/cal_in.json", "w"))
json.dump({d: next_workday(d) for d in dates}, open("/tmp/claude-0/-home-user-B/bc1bd2a3-1ba0-5a86-9b4b-8c9b2f90e18b/scratchpad/sibA/rs3/check/cal_ref.json", "w"))
