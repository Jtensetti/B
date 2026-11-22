"""Same scorer and behavior examples, with the table register disabled before lowering."""
import json
from pathlib import Path
import sys

from lark.exceptions import UnexpectedInput

from b_lang.model import _PARSER

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from score import PUBLIC, full_cases, score


def uses_table(source):
    tree = _PARSER.parse(source if source.endswith("\n") else source + "\n")
    return next(tree.find_data("case_table"), None) is not None


def ordinary_score(path, task, public=False):
    try:
        table = uses_table(Path(path).read_text())
    except UnexpectedInput:
        # The standard compiler supplies the same syntax diagnostic in both conditions.
        return score(path, task, public)
    if not table:
        return score(path, task, public)
    count = len(PUBLIC[task] if public else full_cases(task))
    return {"accepted": False, "passed": 0, "cases": count,
            "error": "Use an ordinary if expression or arithmetic for this language setting."}


if __name__ == "__main__":
    print(json.dumps(ordinary_score(sys.argv[2], sys.argv[1], "--public" in sys.argv[3:])))
