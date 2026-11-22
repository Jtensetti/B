# Why the Boolean pair loop works for every finite input length

The [translation check](validate_boolean_loop.py) compiles a B function that counts consecutive pairs of true flags. It compares the emitted helper's complete Python syntax tree with a small reference, allowing different local names. It also checks that the compiled public function calls that helper. Two deliberately changed loops must fail the structural comparison. Run `python experiments/ordered-history/validate_boolean_loop.py` from the repository root.

For the reference, after processing a prefix of length k, the counter equals the number of adjacent true pairs fully contained in that prefix. The retained bit is its final flag, or false if the prefix is empty.

1. Initially the prefix is empty, the counter is zero and the bit is false.
2. Appending one flag preserves every old pair. It can complete exactly one new pair, and does so precisely when the retained bit and the new flag are both true. The loop adds one exactly in that case, then retains the new flag.
3. By induction the invariant holds at every prefix. After the last flag the counter is the value required by the B expression. A run of three true flags contributes two overlapping pairs.

The structural check transfers that argument to the emitted helper for this one B function under ordinary Python semantics on finite lists of exact booleans. The parser, type checker, wrapper, runtime, adequacy of the source specification and available resources are outside the check. A future backend can produce a correct but structurally different loop. It will need its own equivalence argument.
