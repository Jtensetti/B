import sys, json, math, datetime
sys.path.insert(0, "/tmp/claude-0/-home-user-B/bc1bd2a3-1ba0-5a86-9b4b-8c9b2f90e18b/scratchpad/sibC/cs3/libs/weeks")
from dates import add_days, to_weekday
DAYS = {"Nordic Timber": 12, "Baltic Steel": 9, "Lumo Lighting": 5, "Fabrikk AS": 7, "Textil Partner": 14}
def lev(a, b):
    prev = list(range(len(b)+1))
    for i in range(1, len(a)+1):
        cur = [i] + [0]*len(b)
        for j in range(1, len(b)+1):
            cur[j] = min(prev[j]+1, cur[j-1]+1, prev[j-1]+(a[i-1]!=b[j-1]))
        prev = cur
    return prev[-1]
def match(s):
    best=None; bd=10**9
    for name in sorted(DAYS):
        dd = lev(s, name)
        if dd < bd: bd=dd; best=name
    return best if bd <= 2 else None
def mean(v): return 0.0 if not v else sum(v)/len(v)
def pct(v, p):
    if not v: return 0.0
    s = sorted(v); r = max(math.ceil((p/100.0)*len(s)), 1); return s[min(r, len(s))-1]
def roundup(q, p):
    if q <= 0: return 0
    return (q + p - 1)//p*p
d = json.load(sys.stdin)
today = datetime.date.fromisoformat(d["today"])
orders = {}; unknown = []
for it in d["items"]:
    sup = match(it["supplier"])
    if sup is None:
        unknown.append(it["sku"]); continue
    lead = DAYS[sup]
    series = [0]*28
    for s in d["sales"]:
        if s["sku"] != it["sku"]: continue
        dt = datetime.date.fromisoformat(s["date"])
        off = (dt - today).days
        if -28 <= off <= -1: series[off+28] += s["qty"]
    fc = mean(series[-7:]) if series else 0.0
    if 48 <= today.isocalendar()[1] <= 52: fc *= 1.25
    need = fc*(lead+7) + pct(series, 90) - it["stock"]
    if need > 0:
        q = roundup(math.ceil(need), it["pack"])
        if q * it["price"] >= 500:
            orders[it["sku"]] = {"qty": q, "arrive": to_weekday(add_days(d["today"], lead))}
print(json.dumps({"orders": orders, "unknown": sorted(unknown)}, separators=(",", ":"), ensure_ascii=True))
