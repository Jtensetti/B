# How many questions does a pending edit need?

Four layout policies agree on today's output and differ on two permitted alternatives. Each scripted owner permits neither, either, or both alternatives. We compare two uses of the production B interface across four real B revisions: first identify the complete policy, or let the revised outputs determine which questions to ask. The independent expected verdict checks whether the owner permits every alternative the edit uses.

| Protocol across four owners and four revisions | Decisions matching the owner | New definite answers |
| --- | ---: | ---: |
| Identify policy from scratch before each edit | 16/16 | 32 |
| Decide each edit from scratch | 16/16 | 14 |
| Identify policy, retaining answers across edits for the same owner | 16/16 | 8 |
| Decide edits, retaining answers across edits for the same owner | 16/16 | 8 |

The algebraic refactor needed zero edit-directed questions in every world. Changing just one gap needed one. For the revision changing both gaps, a first negative answer settled rejection early. Across the full sequence an owner eventually had to answer both questions whichever protocol was used. Retaining answers assumes a stable owner and policy. These outcomes count simulated answers. They provide no measurement of human time, comprehension or AI inference cost.

```sh
python experiments/edit-questions/measure.py
```
