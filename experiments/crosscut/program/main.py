"""Read one line of JSON from standard input and print invoices and the report."""
import json
import sys

from shop.catalog import load_catalog
from shop.customers import load_customers
from shop.invoice import invoice_json, make_invoice
from shop.report import report


def main() -> None:
    data = json.loads(sys.stdin.readline())
    catalog = load_catalog(data["catalog"])
    customers = load_customers(data["customers"])
    invoices = [make_invoice(o, catalog, customers) for o in data["orders"]]
    print(json.dumps({"invoices": {i.order_id: invoice_json(i) for i in invoices}, "report": report(invoices)}))


if __name__ == "__main__":
    main()
