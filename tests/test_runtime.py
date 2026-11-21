import math
import pytest
from b_lang.runtime import guard, BBoundaryError


def test_runtime_guard_accepts_supported_types():
    assert guard(1, "Int") == 1
    assert guard(1, "Float") == 1
    assert guard([1, 2], "List[Int]") == [1, 2]
    assert guard("abc", "Text") == "abc"
    assert guard(True, "Bool") is True


@pytest.mark.parametrize("value, typ", [(True, "Int"), ("1", "Float"), (math.inf, "Float"), ([1, "x"], "List[Int]"), (3, "Text")])
def test_guard_rejects(value, typ):
    with pytest.raises(BBoundaryError): guard(value, typ)
