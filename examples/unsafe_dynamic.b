# Works in permissive mode. Strict mode rejects this untyped library call.
use py:json as json
let rendered = json.dumps([1, 2, 3])
print rendered
