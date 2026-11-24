import json, subprocess, sys, math
sys.path.insert(0, "/tmp/claude-0/-home-user-B/bc1bd2a3-1ba0-5a86-9b4b-8c9b2f90e18b/scratchpad/sibA/cs2/libs/calendar")
from workdays import next_workday
inp = json.load(open(sys.argv[1]))
ws = "/tmp/claude-0/-home-user-B/bc1bd2a3-1ba0-5a86-9b4b-8c9b2f90e18b/scratchpad/sibA/cs2"
out = {}
def go_zone(c):
    r = subprocess.run(["go","run","-C",ws+"/xcheck/gozone","."],input=c,capture_output=True,text=True)
    return r.stdout.strip()
print(next_workday("2026-12-24"), next_workday("2026-06-18"), next_workday("2026-04-02"), next_workday("2026-12-31"), file=sys.stderr)
