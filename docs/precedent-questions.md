# Precedent questions

A request such as *"children ride free on Sundays"* names a rule the program already has. In the booking example `free_entry` is already true for a child on Saturday. That existing case is the context for the new one. If a Sunday child is now treated exactly like a Saturday child, the meaning is settled and nobody needs to be asked. If the two still differ somewhere, B has found the booking that needs an answer.

```bee
fn free_entry(child: Bool, day: Text) -> Bool pure = child and day == "sat"
fn ticket(child: Bool, day: Text) -> Int pure = if free_entry(child, day) then 0 else 100
fn fee(child: Bool, day: Text) -> Int pure = if child and day == "sat" then 0 else 10
fn total(child: Bool, day: Text) -> Int pure = ticket(child, day) + fee(child, day)
```

The ticket costs 100 and the booking fee is 10. Somebody waived the fee for Saturday children by repeating the rule's condition instead of calling `free_entry`.

```sh
b ask examples/ask/booking.bee --with examples/ask/sunday.bee
```

```text
also free_entry(true, "sun") keeping seats, recipient
  ticket(true, "sun"): 100 -> 0
  total(true, "sun"): 110 -> 10
  nearest existing case: free_entry(true, "sat")
  fee: 10 here, 0 in the existing case
  total: 10 here, 0 in the existing case
  starts in: fee
  question: total(true, "sun"): 10 or 0?
    10 (as declared): also free_entry(true, "sun") keeping seats, recipient, fee
    0 (like free_entry(true, "sat")): also free_entry(true, "sun") like (true, "sat") keeping seats, recipient
        and in fee: child and day == "sat" -> free_entry(child, day)
```

The answer is a value, not a program. `--answer 10` records that the fee stays by adding `fee` to `keeping`. `--answer 0` records `like (true, "sat")` and replaces the copied condition in `fee` with a call to the rule. Before it offers that edit, B checks that it changes no result of `fee` in the program without the new case. `--apply` writes the chosen revision. The revised program must compile, including the new check, before anything is written. The command exits with 2 while a question is open and 0 once it is settled.

## The `like` clause

```bee
also free_entry(true, "sun") like (true, "sat") keeping seats, recipient
```

`like P` is an executable claim checked by every `check`, `build` and `run`.

1. `P` has the rule's exact parameter types, differs from the new case and was already true before any `also` extended the rule.
2. After the change, every pure native function that shares a parameter name with the rule returns the same value for the new case as for `P`. A shared name denotes the same input. Remaining parameters take the same value on both sides. B tries representative values for them: both Booleans, the program's literals, and for Int, the neighbors of those literals.
3. A function whose body never mentions an input that differs between the two cases agrees trivially. `seats(child, day, available) = available - 1` is accepted without evaluation.

A difference is a compile error naming the first differing outcome and the function where it starts:

```text
E_LIKE: also free_entry(true, "sun") like (true, "sat"): total(true, "sun") = 10, but total(true, "sat") = 0; the difference starts in fee
```

A function B cannot evaluate, for example one with contracts or a foreign call, produces `W_LIKE_UNCOMPARED`. Agreement on sampled values of a parameter used in arithmetic or ordering produces `W_LIKE_SAMPLED`. `--strict` rejects both. For parameters observed only through equality, the representatives cover every equality pattern, as in the [revision checker](executable-changes.md).

## How `b ask` chooses its question

For each `also` without `like`, B compiles the program without that declaration and searches a finite grid of rule inputs drawn from Booleans and the program's literals. It keeps the inputs where the rule was already true and chooses the one that differs from the new case in the fewest positions. The rest follows from the comparison above.

| Result | Meaning |
| --- | --- |
| `settled` | The new case now behaves like the existing one everywhere B compared. B suggests the `like` declaration that records this. |
| `question` | Something still differs. B asks about the differing function that no other differing function calls, and names where the difference starts. |
| `answered` | `keeping` already names every function where the difference starts. |
| `checked` | The declaration already has `like`. |
| `no-change` | The rule was already true for the new case. |
| `no-precedent` | B found no input where the rule was already true. It still lists what the declaration changes. |

The option that keeps the declared meaning adds the starting functions to `keeping`. It is only available when they do not depend on the rule. The option that follows the existing case is only written automatically when each starting function contains the rule's condition verbatim over the same parameter names. Otherwise B names the function to edit and the declaration to add.

## Limits

- **The context is the program.** If a Saturday child already pays the fee, B treats 10 as the settled meaning of "free on Sundays" and asks nothing. An owner who meant 0 for both days has to say so. B cannot tell what the word *free* means beyond the cases the program already contains.
- **Shared names are a convention.** Two parameters named `day` are treated as the same input. Renaming one removes its function from the comparison.
- **Differences can be legitimate.** In the [fixture study](../experiments/precedent-questions/README.md), a Saturday souvenir triggers a question about the souvenir although nobody asked about it. The question is cheap to answer, but it is a question.
- **One precedent.** When several existing cases are equally near, B uses the first. Only one open question can be answered per command.
- **Repairs are textual.** Only a single verbatim copy of the rule's body is replaced. Other spellings of the same condition are reported but not rewritten.
- **Scalar, pure, native functions only.** The search and comparisons use the same evaluator as the revision checker and stop at its work limits.
