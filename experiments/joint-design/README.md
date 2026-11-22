# Does a relation between calls prevent a bad edit?

The first experiment renders two screens with three rows each. A compact screen must have the gaps (1,2,3). An expanded screen must have (2,3,4). Each product edit also requests a specific default for each screen. We compare the first diagnostic on complete, predefined revisions and run an alternative implementation that passes one shared style into the assembler.

| B renderer revision | Every row locally allowed | B joint rule | Typed Python pair rule | Complete layout allowed | Requested screen defaults | Shared assembler meets request |
| --- | --- | --- | --- | --- | --- | --- |
| Original | Yes | Pass | Pass | Yes | Yes | Yes |
| A. Expand dashboard | Yes | Pass | Pass | Yes | Yes | Yes |
| B. Compact exports and cache compact dashboard header | Yes | Pass | Pass | Yes | Yes | Yes |
| A and B together | Yes | Fail | Fail | No | No | Yes |
| Expansion request accidentally leaves old dashboard default | Yes | Pass | Pass | Yes | No | No |

Under the combined edit, the dashboard gaps are (1,3,4). The first B diagnostic includes rank 0 returning 1 and rank 1 returning 3. The Python property checks the spacing difference between rows from the compiled B program. The independent whole-layout oracle directly compares full frames with the two permitted tuples. An ordinary exact test for the requested dashboard and export defaults also catches the forgotten expansion.

The alternative B assembler receives the chosen style once per screen and passes the same value to all three row calls. The single-row renderer also accepts an explicit style parameter, but the two branches of its caller can still pass inconsistent styles. The combined edit exercises that error. The shared-assembler comparison implements the requested behavior through a different construction and omits the cached-header shortcut. If a future edit bypasses that assembler the guarantee must be established again.

## A law about movement can accept the wrong program

A sprite starts at coordinate A and ends at B. In the ideal model its signed displacement is B − A. Adding the same offset to both coordinates leaves that difference unchanged. The pixel-display model first rounds each endpoint down to a whole-pixel boundary. Coordinates are measured in half-pixel units. Shifting by one tick changes the pixel alignment; shifting by two ticks preserves it. [Signed displacement, OpenStax University Physics §3.1](https://openstax.org/books/university-physics-volume-1/pages/3-1-position-displacement-and-average-velocity).

We enumerate all 25 start/end combinations from −2 through 2 ticks. The owner supplies an explicit five-entry display-coordinate table. B and a typed Python property test compare every pair related by a positive one-tick or two-tick shift within the grid. The two direct output oracles score ideal motion and snapped motion separately.

| Implementation | One-tick shift invariant | Two-tick shift invariant | Correct ideal outputs of 25 | Correct snapped outputs of 25 |
| --- | --- | --- | ---: | ---: |
| Signed displacement | Yes | Yes | 25 | 13 |
| Reversed sign | Yes | Yes | 5 | 5 |
| Always stationary | Yes | Yes | 5 | 9 |
| Return the final coordinate | No | No | 5 | 6 |
| Snap the two endpoints before subtracting | No | Yes | 13 | 25 |
| Subtract first, then snap | Yes | Yes | 13 | 19 |

A reversed sign satisfies both invariances on the full grid. A correct pixel implementation fails the finer invariance. The original review question therefore has two parts: whether the requirement fits the measurement and whether the chosen properties distinguish the intended calculation from plausible alternatives.

Run `python experiments/joint-design/measure.py` with the B package installed. The output includes every verdict and the first failing pair. All evaluations use predefined edits and a finite grid. The trials measure diagnostic sensitivity and specificity, with no model-generated patches or repair-turn estimates.
