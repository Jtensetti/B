# Batch helper: argv[1] is the libs/payroll directory. Reads "gross table" per line on stdin,
# writes the withholding for each line.
import sys

sys.path.insert(0, sys.argv[1])
from withholding import withholding  # noqa: E402

for line in sys.stdin:
    gross_text, table_text = line.split()
    print(withholding(float(gross_text), int(table_text)))
