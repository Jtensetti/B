import random, json, datetime, sys
seed = int(sys.argv[1]); random.seed(seed)
today = datetime.date(2026,1,1) + datetime.timedelta(days=random.randint(0,900))
sup = ["Nordic Timber","Baltic Steel","Lumo Lighting","Fabrikk AS","Textil Partner","Nope Co"]
items = []; sales = []
for i in range(random.randint(0,12)):
    sku = f"SKU-{random.randint(0,99):02d}-{'é' if random.random()<0.1 else 'x'}{i}"
    items.append({"sku": sku, "supplier": random.choice(sup), "stock": random.randint(0,60), "pack": random.randint(1,12), "price": random.choice([1, 2.5, 10, 25.75, 99])})
    for _ in range(random.randint(0,30)):
        off = random.randint(-40, 3)
        sales.append({"sku": sku, "date": (today + datetime.timedelta(days=off)).isoformat(), "qty": random.randint(1,9)})
print(json.dumps({"today": today.isoformat(), "items": items, "sales": sales}))
