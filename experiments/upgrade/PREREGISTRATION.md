# Pre-registration: the upgrade trial

Committed before any solver runs. Results will be added below the line, whatever they are.

## Why

Five trials ([summary](../../docs/vision.md#measured-so-far)) produced no wrong output in either language. In the [ambiguity trial](../ambiguity/PREREGISTRATION.md) every solver read the change correctly, so B's questions had nothing to prevent. The errors left to measure are the ones that careful reading of the program cannot prevent. A library that changes behavior underneath the program is the clearest case. B checks an `example` on an imported function every time the program is compiled or run ([decisions about libraries](../../docs/library-examples.md)). A Python test checks only when someone chooses to run it.

## Hypothesis

H2. When a library changes behavior in an upgrade that nobody mentions, B solvers deliver fewer wrong quotes than typed Python solvers over the steps after the upgrade.

## Design (fixed now)

- **Task.** A parcel quote program using libraries from two ecosystems: a Python tariff library (`tariff.py` in the workspace, [v1](lib/v1/)) and the npm package fastest-levenshtein. The [build brief](steps/build.md) is complete. It says the customer pays the carrier's price excluding VAT plus 25 % VAT, that tariff is maintained by another team, and that a bot upgrades it in the workspace from time to time. Both languages get the same brief.
- **Steps.** Build, then [change 1](steps/change1.md) (fuel surcharge). Before change 2, tariff is replaced in every workspace by [v2](lib/v2/), with its changelog, without a message. In v2, `base_price` returns the price *including* VAT. That is one line among five in the changelog. Then [change 2](steps/change2.md) (quantity) and [change 3](steps/change3.md) (discount over 20 kg). The change messages do not mention the upgrade.
- **Owner's intent.** The customer's price does not change because of the upgrade. The [oracle](oracle.py) computes it from the tariff tables directly.
- **Solvers.** Three Claude Haiku instances per language in separate workspaces, same rules as the ambiguity trial: one QUESTION allowed per step, answered truthfully from the intent in one sentence. B solvers read [B for models](../../docs/for-models.md), unchanged from the commit of this file. Python solvers write typed Python. Both get node_modules and are told to test their work.
- **Grading.** 24 hidden orders (18 quotable, 6 unknown) after every step, with a tolerance of 0.02 kr. A program that does not run scores 24 wrong. Primary score: wrong quotes summed over changes 2 and 3. Output tokens are measured as before.
- **Also recorded.** Whether each solver wrote a check on tariff's behavior (an `example` in B, a test in Python), and whether it noticed the upgrade.

## Kill criterion

If B solvers deliver as many wrong quotes as Python solvers or more, summed over changes 2 and 3, H2 fails. Library examples then stay a tool, and B no longer claims to reduce errors from upgrades. If no solver in either language delivers a wrong quote, H2 also fails: there was nothing to prevent.
