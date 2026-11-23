# Units: relations that never change

A kilometer is always 1000 meters, an inch always 25.4 mm, an hour always 3600 seconds and a kilowatt-hour always 3.6 MJ. B knows these relations. It checks the dimension of every quantity before the program runs.

```bee
fn speed(distance: Length, time: Duration) -> Speed pure = distance / time

let trip = 5 km + 300 m
print trip as m                               # 5300.0
print speed(1 mil, 45 min) as km per h        # 13.333333333333332
print (20 degC + 5 dK) as degF                # 77.0
print 10 USD * (10.5 SEK per USD) as kr       # 105.0
```

And these are compile errors:

```text
let x = 5 km + 2 kg        E_UNIT: Cannot add Length and Mass
let x = 100 SEK + 5 USD    E_UNIT: Cannot add Money[SEK] and Money[USD]
let x = 20 degC + 5 degC   E_UNIT: two absolute temperatures only have a difference, written in dK, dC or dF
print 5 km                 E_UNIT: print needs a plain number, got Length; convert it with 'as'
let x = 1 month            E_UNIT: months and years have no fixed length
```

## Syntax

- **A quantity literal** is a number followed by a unit: `5 km`, `19.5 kr`, `-5 degC`. A compound unit uses `per`: `90 km per h`, `10.5 SEK per USD`. Other products come from arithmetic: `3 kW * 2 h` is energy.
- **`x as unit`** gives a plain number in that unit. A quantity has no number until you say which unit, so `print` and foreign calls require `as`.
- **Types:** `Length`, `Mass`, `Duration`, `Area`, `Volume`, `Speed`, `Acceleration`, `Frequency`, `Force`, `Energy`, `Power`, `Pressure`, `Current`, `Charge`, `Voltage`, `Resistance`, `Data`, `DataRate`, `Angle`, `Density`, `Temperature`, `TemperatureDifference`, `Amount`, `Money[SEK]` and `Rate[SEK, USD]` (SEK per USD). There are Swedish aliases: `Längd`, `Sträcka`, `Massa`, `Vikt`, `Tid`, `Yta`, `Volym`, `Hastighet`, `Energi`, `Effekt`, `Tryck`, `Temperatur`, `Pengar[SEK]` and `Kurs[SEK, USD]`.
- **Zero needs no unit.** `d > 0` is accepted for any quantity `d`, because zero is zero in every unit.
- Units can only appear after a number, `as` or `per`, so a variable called `m` or `h` does not clash with them.

## What B knows

| Kind | Units |
| --- | --- |
| Length | m, km, dm, cm, mm, um, nm, **mil** (Swedish, 10 km), inch, ft, yd, mi, nmi, au |
| Mass | kg, g, mg, ug, t, **hg**, lb, oz |
| Time | s, ms, us, ns, min, h, day (24 h), week |
| Area, volume | m2, cm2, mm2, km2, ha, m3, cm3, l, **dl**, cl, ml, gal (US) |
| Speed, frequency | mph, knot, any length `per` time, Hz, kHz, MHz, GHz, rpm |
| Force, energy, power, pressure | N, kN, J, kJ, MJ, Wh, kWh, MWh, cal, kcal, W, kW, MW, hp (metric), Pa, hPa, kPa, bar, atm |
| Electricity, chemistry, light | A, mA, C, mAh, V, mV, kV, ohm, mol, cd |
| Data | bit, kbit, Mbit, Gbit, B, kB, MB, GB, TB, KiB, MiB, GiB, TiB |
| Angle | rad, deg, turn |
| Temperature | K, degC, degF (absolute); dK, dC, dF (differences) |
| Money | 24 ISO currency codes, **kr** = SEK, **öre** = 0.01 SEK, cent = 0.01 EUR |

Every factor is an exact fraction from the unit's definition. The inch has been exactly 25.4 mm since 1959, the pound exactly 0.45359237 kg, the metric horsepower 735.49875 W. The exception is `deg` and `turn`, which depend on π rounded to a Float.

## What B deliberately does not know

- **Exchange rates.** USD is always US dollars and SEK always Swedish kronor, but the rate between them changes. Every currency is its own dimension, so money only crosses currencies through a rate the program states, such as `Rate[SEK, USD]`.
- **Which kr.** Norway, Denmark and Iceland also write *kr*. In B, `kr` means SEK. Other kronor are written NOK, DKK and ISK.
- **Months and years as durations.** A month is 28–31 days and a year 365 or 366. They are calendar questions (see `know calendar`), not units.
- **A calendar day.** `day` is 24 hours. A day with a daylight-saving change is 23 or 25 hours on the clock.

## How it runs

The units are checked and then erased. Every quantity becomes a Float in its SI base unit (meters, kilograms, seconds, kelvin, one unit of the currency), and BIR contains no units. A program without units is passed through unchanged. Values known at compile time are computed with exact fractions, so `100 degC as degF` is exactly `212.0`. Values computed at runtime are Float arithmetic: a fare of 25 km at 12 kr per mil prints `29.999999999999996`.

## Limits

- **Money is Float at runtime.** That is fine for estimates but wrong for bookkeeping. Exact decimal money is the most important next step.
- **No quantities in lists, dictionaries or functions defined by examples yet.** Convert with `as` first.
- Foreign calls see plain numbers only, so `as` is required at the boundary. A Python function that takes meters and one that takes feet look the same to B. This is exactly the kind of false friend the vision describes.
