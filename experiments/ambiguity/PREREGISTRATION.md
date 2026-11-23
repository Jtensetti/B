# Pre-registration: the ambiguity trial

Committed before any solver runs. Results will be added below the line, whatever they are.

## Why

Four trials ([journey](../journey/README.md), [shipping](../shipping/README.md), [releases](../releases/README.md)) produced no errors in either language. Their specifications were complete, and the solvers tested their own work. Real changes are often incomplete. "Children ride free on Sundays too" can mean the ticket only, or the ticket and the booking fee. B was built for this: `also` states the change as an extension of an existing rule, and `b ask` compares the new case with the case the rule already covered and reports the concrete booking where the two readings part. Python has no such tool.

## Hypothesis

H1. Over three ambiguous changes, B solvers deliver fewer wrong totals on the hidden fixtures than typed Python solvers.

## Design (fixed now)

- **Task.** A booking price calculator. It reads `{"bookings": [{"id", "child": Bool, "day": "mon".."sun", "member": Bool}]}` and writes `{"totals": {"<id>": <kr>}}`. The build specification is complete: a ticket costs 100 kr and the booking fee is 10 kr. Children pay no ticket and no booking fee on Saturdays. Members get 20 kr off the ticket, but not below 0.
- **Three changes, each worded as an owner would say it, each with two reasonable readings.** The owner's intent is written in the oracle now:
  1. "Children ride free on Sundays too." Intent: like Saturday, so no ticket and no fee. Other reading: ticket only, total 10 kr.
  2. "The booking fee goes up to 15 kr." Intent: only bookings that paid a fee pay 15. Children on Saturdays and Sundays still pay none. Other reading: everyone pays 15.
  3. "Members get 10 percent off instead of 20 kr." Intent: 10 percent off the ticket, not the fee. Other reading: 10 percent off the total.
- **Questions.** At every step a solver may reply with one QUESTION. The owner answers truthfully from the intent above, in one sentence, without volunteering anything beyond the question.
- **Solvers.** Three Claude Haiku instances per language, in separate workspaces. B solvers are pointed at [B for models](../../docs/for-models.md). Its section on changing a rule (`also`, `b ask`) is added before the trial starts. Python solvers get the same task text.
- **Grading.** 28 hidden fixtures cover every child, day and member combination. Score: the number of wrong totals after each change. Output tokens are measured as before.

## Kill criterion

If B solvers deliver as many wrong totals as Python solvers or more, summed over the three changes, H1 fails. B's question tooling would then be no better than a model reading the request carefully, and the roadmap should drop the ambition that B reduces errors in changes.

---

## Results (added after the run)

Six Claude Haiku solvers, three per language, built the calculator and then took the three changes in order. The hidden fixtures were graded after every step. The grader's log is in [`results/grades.txt`](results/grades.txt), the final programs in [`solutions/`](solutions/), and the work per step in [`results/work.json`](results/work.json).

| | Build | Change 1 | Change 2 | Change 3 | Wrong, changes 1–3 | Questions |
| --- | --- | --- | --- | --- | --- | --- |
| B (3 solvers) | 0 | 0 | 0 | 0 | **0** | 0 |
| Python (3 solvers) | 0 | 0 | 0 | 0 | **0** | 0 |

Output tokens over all four steps were 12 214, 20 070 and 12 754 for B (45 038 in total), and 11 883, 15 857 and 22 621 for Python (50 361 in total). B used 0.89 times Python's tokens. With three solvers per language, that difference is within the spread between solvers.

**H1 fails.** B delivered as many wrong totals as Python: none. The kill criterion applies as written. B's question tooling has not been shown to be better than a model that reads the request carefully, so the roadmap no longer claims that B reduces errors in changes.

### Why there were no errors

The ambiguity never reached the code. All six builds put "children on Saturdays" into one condition that waives both the ticket and the fee: `free_entry` in B, `if child and day == "sat": return 0` in Python. Widening that condition to Sunday gives the owner's reading in both languages without a decision being made. In the same way, a fee that already skipped free bookings stayed skipped when it rose to 15 kr. A discount that was already on the ticket stayed on the ticket when it became a percentage. Every solver chose the reading the owner meant, and none asked.

`b ask` was run by two of the three B solvers on change 1. It found that Saturday settled the meaning and asked nothing, which was correct. The third solver edited the condition directly. `also` and `b ask` fit change 1 only. Changes 2 and 3 alter numbers, not a Boolean rule, and B has no question tooling for them.

### What this does and does not show

- It shows that a well-factored first build absorbs this kind of ambiguity in either language. The task was too small to produce the second reading by accident.
- It does not show that B's questions are useless. They would matter where the existing code does not already encode the analogy, for example when the fee and the ticket have separate conditions, as in the guide's own example. This trial did not create that situation, and running a new trial designed so that B wins would be p-hacking after a failed hypothesis.
- Together with the four earlier trials, 22 solver runs have now produced no wrong output in either language. "Fewer errors" has not been measured as an advantage, because these tasks do not produce errors for current models.
