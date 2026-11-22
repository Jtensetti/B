import json
from pathlib import Path

import pytest

from b_lang.cli import main
from b_lang.clarify_cli import MAX_REQUEST_BYTES

FIXTURES = Path(__file__).resolve().parents[1] / "examples/intent"
BASE = FIXTURES / "layout.bee"
REQUEST = FIXTURES / "layout.json"
EDIT = FIXTURES / "compact.bee"


def invoke(capsys, *args, code=0, request=REQUEST):
    assert main(["clarify", str(BASE), str(request), *args, "--json"]) == code
    return json.loads(capsys.readouterr().out)


def response(rank, gap, allowed):
    return json.dumps({"inputs": {"rank": rank}, "result": gap, "allowed": allowed})


def test_round_trip_and_equivalent_refactor(capsys):
    report = invoke(capsys)
    q = report["question"]
    assert q["inputs"] == {"rank": 0} and q["result"] == 2
    first = ["--answer", response(0, 2, True)]
    assert invoke(capsys, *first)["question"]["inputs"] == {"rank": 2}
    assert invoke(capsys, *first, "--answer", response(2, 4, False))["survivors"] == ["compact_choice"]
    assert invoke(capsys, "--edit", str(BASE))["status"] == "approve"
    assert main(["clarify", str(BASE), str(REQUEST)]) == 0
    assert "May gap(rank=0) return 2?" in capsys.readouterr().out


def test_edit_gate_uncertainty_rejection_and_approval(capsys):
    args = ["--edit", str(EDIT)]
    assert invoke(capsys, *args, code=2)["status"] == "needs-answer"
    assert invoke(capsys, *args, "--answer", response(0, 2, None), code=2)["status"] == "inconclusive"
    accepted = invoke(capsys, *args, "--answer", response(0, 2, True))
    assert accepted["status"] == "approve" and len(accepted["survivors"]) == 2
    assert invoke(capsys, *args, "--answer", response(0, 2, False), code=1)["status"] == "reject"
    error = invoke(capsys, *args, "--strategy", "minimax", code=2)
    assert error["error"]["code"] == "E_CLARIFY_INPUT"


def test_file_answers_are_replayed_with_new_answers(capsys, tmp_path):
    data = json.loads(REQUEST.read_text())
    data["answers"] = [json.loads(response(0, 2, True))]
    path = tmp_path / "answered.json"
    path.write_text(json.dumps(data))
    assert invoke(capsys, "--answer", response(2, 4, True), request=path)["survivors"] == ["both_choices"]
    assert invoke(capsys, "--answer", response(0, 2, False), request=path, code=2)["status"] == "inconsistent"


def test_abstention_keeps_options(capsys):
    first = ["--answer", response(0, 2, None)]
    assert invoke(capsys, *first)["question"]["inputs"] == {"rank": 2}
    final = invoke(capsys, *first, "--answer", response(2, 4, None), code=2)
    assert final["status"] == "undetermined" and len(final["survivors"]) == 4


@pytest.mark.parametrize("raw", [
    b'{"function":"gap","function":"other"}', b'{"outputs":[]}', b'["not a request"]',
    b'{"function":', b'\xff', b'{"function":"gap","axes":{},"outputs":[1],"candidates":{},"ansers":[]}',
])
def test_malformed_requests_have_a_structured_error(capsys, tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_bytes(raw)
    report = invoke(capsys, code=2, request=path)
    assert report["status"] == "error" and report["error"]["code"] == "E_CLARIFY_INPUT"


def test_oversized_and_malformed_responses_fail_closed(capsys, tmp_path):
    path = tmp_path / "long.json"
    path.write_bytes(b" " * (MAX_REQUEST_BYTES + 1))
    assert invoke(capsys, request=path, code=2)["error"]["code"] == "E_CLARIFY_LIMIT"
    assert invoke(capsys, "--answer", '{"allowed":false}', code=2)["error"]["code"] == "E_CLARIFY_INPUT"


def test_minimax_cli_reports_a_conditional_bound(capsys):
    report = invoke(capsys, "--strategy", "minimax")
    assert report["planning"]["worst_case_remaining_questions"] == 2
    assert report["planning"]["used"] == "minimax"
    assert main(["clarify", str(BASE), str(REQUEST), "--strategy", "minimax"]) == 0
    assert "At most 2" in capsys.readouterr().out
