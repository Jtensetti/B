Write a callable function named "ledger" taking a list of weighing records and an integer allowance. Every record is a dictionary from text to integers. Return one dictionary with these integer fields:

- "weighed" counts all records, even incomplete ones.
- "incomplete" counts records missing "gross", "tare" or both.
- "over" counts complete records for which gross minus tare exceeds the allowance.
- "extra" sums the amounts by which those records exceed the allowance.

A zero is a valid reading. Negative readings and allowances can occur. Other keys have no bearing on the result. An empty list returns four zeros.
