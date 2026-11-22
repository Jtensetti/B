B native integer functions use `fn name(x: Int) -> Int pure = expression`. Arithmetic includes `+`, `-`, `*` and integer remainder `%`. A Boolean condition can use `and` or `or`. You can call a helper defined earlier.

A conditional can be written `if x < 0 then 5 else if x == 4 then 9 else 3`. The same ordered choices can be written `cases x { < 0 => 5; == 4 => 9; else => 3 }`. A table tests a named value against literals, uses its first matching row, and needs a fallback. The result of a row is an ordinary B expression. Arithmetic can also be used directly without either branching form.
