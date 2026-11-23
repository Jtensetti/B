# What B knows

A language can know things. *A week is Monday to Sunday. The weekend is Saturday and Sunday.* These are not program logic. They are shared truths, and almost every program about tickets, opening hours or payroll restates them by hand.

```bee
know kalender

fn pris(barn: Bool, dag: Text) -> Int pure by examples
example pris(false, "måndag") == 100
example pris(true, "lördag") == 0
```

`know kalender` brings in B source that ships with the compiler ([`b_lang/truths/kalender.bee`](../b_lang/truths/kalender.bee)):

```bee
domain dag: "måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"
group helg of dag: "lördag", "söndag"
group vardag of dag: "måndag", "tisdag", "onsdag", "torsdag", "fredag"
```

`know calendar` is the English version with `day`, `weekend`, `weekday`, `month`, quarters and seasons. B's knowledge is written in B, so it can be read, checked and extended like any program.

## Knowledge changes what is simple

A `group` is a named subset of an input's values. In code, `dag in helg` is a test like any other. In a function defined by examples, a known group counts as **one test**, just like `dag == "lördag"`. Knowing the word *helg* therefore makes a weekend rule as simple as a Saturday rule.

The Saturday program above settles as `if barn and dag == "lördag" then 0 else 100` after four answers. Then the requirement changes:

```bee
example pris(true, "söndag") == 0 was 100
```

B asks **nothing** and derives `if barn and dag in helg then 0 else 100`. With Saturday and Sunday both free, the simplest explanation uses the word B already knows. Without `know kalender` the same change needs another question, and the rule lists the two days separately.

| Hidden policy | Questions without knowledge | With `know calendar` |
| --- | ---: | ---: |
| Children free on weekends | 6 | 4 |
| Children free on Saturdays | 5 | 4 |
| Children free every day | 2 | 3 |

Each run starts from the same two examples, `price(false, "mon") == 100` and `price(true, "sat") == 0`. All six runs end with the exact policy. Knowledge is not free: every group is one more reading to rule out, and the third policy needs one extra question. A tested reproduction is in [`tests/test_knowledge.py`](../tests/test_knowledge.py).

## Rules

- `group NAME of PARAM: "a", "b"` takes Text values. When `PARAM` has a domain, every member must be in it. Group names are unique.
- `x in NAME` works on any Text expression. The compiler rewrites it as equality tests before type checking, so it adds nothing to BIR.
- `know TOPIC` may appear more than once. A knowledge file may only declare domains and groups.
- As everywhere in B, a parameter name is the input's identity. `know kalender` gives any parameter called `dag` the seven Swedish weekdays.
- Names may use any letters, including Swedish ones, provided they are already in normalized Unicode form.

## Limits and next steps

- **Two topics only.** Calendar facts in English and Swedish. Units, currencies, countries and holidays are obvious next candidates, but each needs a source and a maintenance story. Holidays change every year.
- **No relations yet.** B knows the order of the days and that Sunday is a weekend day. It does not know that Monday follows Sunday, that a month has 28–31 days, or that 60 minutes make an hour. Relations like these need more than groups: functions that B ships and checks, with examples as their tests.
- **Shared names are a convention.** A parameter called `dag` that holds something else will get a weekday domain anyway.
