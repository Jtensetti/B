import math
import pytest
from b_lang.runtime import guard, BBoundaryError


def test_runtime_guard_accepts_supported_types():
    assert guard(1, "Int") == 1
    assert guard(1, "Float") == 1.0
    assert type(guard(1, "Float")) is float
    assert guard([1, 2], "List[Float]") == [1.0, 2.0]
    assert guard([1, 2], "List[Int]") == [1, 2]
    assert guard("abc", "Text") == "abc"
    assert guard(True, "Bool") is True


@pytest.mark.parametrize("value, typ", [(True, "Int"), ("1", "Float"), (math.inf, "Float"), ([1, "x"], "List[Int]"), (3, "Text")])
def test_guard_rejects(value, typ):
    with pytest.raises(BBoundaryError): guard(value, typ)


def test_runtime_normalizes_nested_dynamic_float_at_boundary():
    result = guard([[1, 2], [3]], "List[List[Float]]")
    assert result == [[1.0, 2.0], [3.0]]
    assert all(type(x) is float for group in result for x in group)


def test_float_conversion_rejects_unrepresentable_int():
    with pytest.raises(BBoundaryError):
        guard(10 ** 2000, "Float")
