import pytest

from b_lang.runtime import BBoundaryError, guard


@pytest.mark.parametrize(("element_type", "good", "bad"), [
    ("Int", 1 << 100, True),
    ("Bool", True, 1),
    ("Text", "B", b"B"),
])
def test_scalar_list_snapshot_and_first_mismatch(element_type, good, bad):
    source = [good, good]
    checked = guard(source, f"List[{element_type}]")
    source.clear()
    assert checked == [good, good]

    with pytest.raises(BBoundaryError) as error:
        guard([good, bad, None], f"List[{element_type}]")
    assert str(error.value) == f"Expected {element_type} at boundary, got {type(bad).__name__}: {bad!r}"


def test_scalar_list_guard_requires_exact_python_types():
    class TaggedInt(int):
        pass

    class TaggedList(list):
        pass

    with pytest.raises(BBoundaryError, match="Expected Int at boundary, got TaggedInt"):
        guard([TaggedInt(1)], "List[Int]")
    with pytest.raises(BBoundaryError, match=r"Expected List\[Int\] at boundary, got TaggedList"):
        guard(TaggedList([1]), "List[Int]")
