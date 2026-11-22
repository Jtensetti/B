B native integer functions use `fn name(x: Int) -> Int pure = expression`. Arithmetic includes `+`, `-`, `*` and integer remainder `%`. A Boolean condition can use `and` or `or`. You can call a helper defined earlier.

A conditional can be written `if x < 0 then 5 else if x == 4 then 9 else 3`. Each test can refer to the inputs by name. The first true condition selects its result, and the final `else` gives the fallback. The result of a branch is an ordinary B expression. Arithmetic can also be used directly without branching.
