# Can a question about one result uncover a rule shared by several calls?

Three row ranks each have two possible gaps. Under one product requirement the designer selects a single style for the whole screen. This allows two complete layouts, (1,2,3) and (2,3,4). A second requirement lets every row select independently, allowing eight layouts. Both specifications give exactly the same answer to every possible question about one row, even with exhaustive input and output coverage.

The B experiment passes two equivalent one-row descriptions to `compare`, then supplies an edited B function producing (1,3,4). B reports `equivalent-on-grid` for the descriptions and `approve` for the pending edit. That is correct for the supplied local predicates. The independent whole-screen oracle rejects the mix in the one-style world. Encoding each complete style as a separate policy would preserve this distinction, but a user who says “either style is allowed” is not choosing between those two policies.

An independent enumerator projects the complete layouts onto every subset of ranks, beginning with subsets of size one. It finds no separating single-row question. At size two it finds six separating patterns. One concrete question is “Can rank 0 have gap 1 and rank 1 have gap 3 **on the same screen**?” A positive answer selects independent styles. A negative answer selects a common style within this two-policy comparison.

A constructed parity control allows a layout if an even number of rows choose the larger gap. All single-row and two-row patterns are possible in both the parity and unrestricted worlds. Four three-row patterns separate them. Pairwise questioning therefore has a concrete limit too.

```sh
python experiments/layout-coherence/measure.py
```

The enumerator uses all complete layouts and an exhaustive search, which grows exponentially. It is a reference experiment for three rows. A practical follow-up is to expose two scoped calls to a contract, then compare with simpler designs such as passing a shared style parameter or checking a complete layout value. Properties that constrain groups of executions have been studied formally. [Clarkson and Schneider, Hyperproperties](https://www.cs.cornell.edu/fbs/publications/Hyperproperties.JCS.pdf).
