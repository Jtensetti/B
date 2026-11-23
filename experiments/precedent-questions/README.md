# Precedent questions: seven bookings, one request

Every program admits children free on Saturday through `free_entry`, with a ticket of 100 and a booking fee of 10. The request is the same in all seven programs: *children ride free on Sundays*, written as `also free_entry(true, "sun")`. The question is whether B can tell when that request is ambiguous, and whether a single answer then produces a working program.

[check.py](check.py) builds the programs, runs `b ask`, executes every offered answer and runs `ask` again on the result. [results.json](results.json) holds the output. A test checks that the file is current.

| Program | Sunday total, rule only | Saturday total | `b ask` | Answers |
| --- | ---: | ---: | --- | --- |
| A Fee waiver repeats the Saturday condition | 10 | 0 | **10 or 0?** | 10: `keeping fee`. 0: `like` plus an automatic repair of `fee`. Both run and settle. |
| B Flat fee | 10 | 10 | settled | `like (true, "sat")` compiles under `--strict` |
| C Fee waiver calls the rule | 0 | 0 | settled | same |
| D Fee waiver already covers the weekend | 0 | 0 | settled | same |
| E Sunday surcharge of 20 | 30 | 10 | **30 or 10?** | 30: `keeping surcharge`. 10: B names `surcharge` as the function to edit. |
| F Saturday souvenir | 10 | 10 | **"none" or "pin"?** | "none": `keeping souvenir`. "pin": B names `souvenir`. |
| G Rule never true before | 10 | 110 | no precedent | B lists the changes only |

In A, B found the exact booking where the two reasonable readings part, asked for one number and wrote either program. In B, C and D, the Saturday case settles the meaning, so no question is asked. Program B is the case from the project brief: if a Saturday child already pays the fee, B concludes that a Sunday child pays it too. That conclusion is only as good as the existing program. If the owner meant 0 on both days, B misses the ambiguity.

E and F show the other side. A Sunday surcharge is a real question about a free child. A souvenir handed out on Saturdays probably is not, but B asks anyway because the souvenir function shares the `child` and `day` inputs. In both cases B can only write the answer that keeps the declared meaning. The other answer needs a hand edit, and B names the function.

## What this does not show

The seven programs, the request and the expected readings were written by the same author as the mechanism. No model or human was asked to use `b ask`, and nothing here measures tokens, time or the cost of a wrong guess. The same comparison could be written as a Python test harness that binds functions by parameter name. B's contribution is narrower: the precedent is part of the declaration, every compilation checks it, and the answer is written back as code. Whether that saves a revision cycle in practice needs a trial with unseen programs, where a solver gets the request alone and the score counts questions, answers, retries and wrong totals.

## Reproduce

```sh
python experiments/precedent-questions/check.py
```
