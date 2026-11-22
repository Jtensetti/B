"""Compare observation-first discovery with reading the symbolic body directly."""
import json
from pathlib import Path

from b_lang import affine
from b_lang.compiler import compile_b
from b_lang.proposals import report


def cases():
    trial = Path(__file__).resolve().parent
    yield "booking", "accounted", (trial.parents[1] / "examples/conservation.bee").read_text()
    for task, name in (("ledger", "balance"), ("spacing", "gap")):
        yield task, name, (trial / task / "program.bee").read_text()
    yield "double", "f", "fn f(x: Int) -> Int = 2 * x"
    yield "rare exception", "f", "fn f(x: Int) -> Int = if x == 10007 then x + 1 else x"
    yield "visible exception", "f", "fn f(x: Int) -> Int ensures result == x = if x == 17 then x + 1 else x"


if __name__ == "__main__":
    for label, name, source in cases():
        program = compile_b(source).ir
        functions = {s.name: s for s in program.statements if s.op == "fn"}
        direct = affine.implementation(functions[name], functions, {}, expand_bodies=True)
        observed = report(program, name)
        print(json.dumps({
            "case": label, "direct_symbolic_body": direct.form.render() if direct else None,
            "observations": observed["observations_count"], "proposed": observed["proposed_contract"],
            "proposal_verification": observed["verification"]["status"],
            "declared_counterexample": observed["declared_counterexample"],
        }))
