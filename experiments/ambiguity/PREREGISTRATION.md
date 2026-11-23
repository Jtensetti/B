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
