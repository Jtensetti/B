import subprocess, sys, os
sys.path.insert(0, "/tmp/claude-0/-home-user-B/bc1bd2a3-1ba0-5a86-9b4b-8c9b2f90e18b/scratchpad/sibA/cs2/libs/calendar")
from workdays import next_workday
NM = "/tmp/claude-0/-home-user-B/bc1bd2a3-1ba0-5a86-9b4b-8c9b2f90e18b/scratchpad/sibA/cs2/node_modules/fastest-levenshtein/mod.js"
cases = [l.rstrip("\n").split("\t") for l in open("cases.txt") if l.strip()]
cs = open("cs_out.txt").read().split("\n")
rs = open("rs_out.txt").read().split("\n")
gi = 0; wd_bad = geo_bad = 0; geo_n = wd_n = 0
for i, c in enumerate(cases):
    if c[0] == "geo":
        geo_n += 1
        if abs(float(rs[gi]) - float(cs[i])) > 1e-9 * max(1, abs(float(rs[gi]))): geo_bad += 1
        gi += 1
    elif c[0] == "wd":
        wd_n += 1
        if next_workday(c[1]) != cs[i]: wd_bad += 1; print("WD mismatch", c, cs[i])
print("geo n/bad", geo_n, geo_bad)
print("wd n/bad", wd_n, wd_bad)
lev = [c for c in cases if c[0] == "lev"]
js = f"const L=require('{NM}');const lines=require('fs').readFileSync(0,'utf8').split('\\n').filter(Boolean);console.log(lines.map(l=>{{const [a,b]=l.split('\\t');return L.distance(a,b)}}).join('\\n'))"
nodeout = subprocess.run(["node", "-e", js], input="\n".join(f"{c[1]}\t{c[2]}" for c in lev) + "\n", capture_output=True, text=True).stdout.split()
csl = [cs[i] for i, c in enumerate(cases) if c[0] == "lev"]
mis = [(c[1], c[2], a, b) for c, a, b in zip(lev, nodeout, csl) if a != b]
print("lev n/bad", len(lev), len(mis), mis[:3])
bs = [c for c in cases if c[0] == "base"]
os.makedirs("gobase", exist_ok=True)
open("gobase/main.go", "w").write('''package main
import ("bufio";"fmt";"os";"strconv";"strings";"example.com/tariff")
func main(){ sc:=bufio.NewScanner(os.Stdin); for sc.Scan(){ p:=strings.Split(sc.Text(),"\\t"); z,_:=strconv.Atoi(p[0]); w,_:=strconv.ParseFloat(p[1],64); fmt.Println(strconv.FormatFloat(tariff.BasePrice(z,w),'g',-1,64)) } }
''')
open("gobase/go.mod", "w").write("module gobase\n\ngo 1.22\n\nrequire example.com/tariff v0.0.0\n\nreplace example.com/tariff => ../../libs/tariff\n")
go = subprocess.run(["go", "run", "."], cwd="gobase", input="\n".join(f"{c[1]}\t{c[2]}" for c in bs) + "\n", capture_output=True, text=True)
gout = go.stdout.split()
csb = [cs[i] for i, c in enumerate(cases) if c[0] == "base"]
badb = [(c, a, b) for c, a, b in zip(bs, gout, csb) if abs(float(a) - float(b)) > 1e-9]
print("base n/bad", len(bs), len(badb), badb[:3], go.stderr[:300])
