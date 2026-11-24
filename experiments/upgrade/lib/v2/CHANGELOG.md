# tariff changelog

## 2.0.0
- Python 3.8 is no longer supported.
- Added Iceland (zone 2).
- `zone()` ignores surrounding whitespace.
- `base_price()` returns the consumer price, including 25 % VAT, to match carrier invoices.
- Internal: tariff tables moved to module constants.

## 1.4.2
- Fix: `zone()` accepts lowercase country codes.

## 1.4.0
- Added the Netherlands and Great Britain.

## 1.3.0
- `base_price()` rounds to whole öre.
