import random, datetime, json
random.seed(7)
L = []
for _ in range(3000):
    L.append("geo\t%f\t%f\t%f\t%f" % (random.uniform(-80,80), random.uniform(-180,180), random.uniform(-80,80), random.uniform(-180,180)))
for _ in range(2000):
    L.append("base\t%d\t%f" % (random.randint(1,4), random.uniform(0,60)))
for _ in range(20):
    L.append("base\t%d\t%f" % (random.randint(1,4), random.choice([0,0.5,1,1.0001,1.5,2,2.5,30.25])))
alpha = "abcAB ."
rnd = lambda n: "".join(random.choice(alpha) for _ in range(random.randint(0,n)))
for _ in range(3000):
    L.append("lev\t%s\t%s" % (rnd(12), rnd(12)))
L.append("lev\t%s\t%s" % ("x"*40+"ab", "x"*39+"ba"))
d = datetime.date(2025,1,1)
for i in range(800):
    L.append("wd\t%s" % (d + datetime.timedelta(days=i)).isoformat())
open("cases.txt","w").write("\n".join(L)+"\n")
