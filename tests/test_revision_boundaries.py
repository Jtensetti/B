import pytest

from b_lang.compiler import compile_b
from b_lang.revisions import check_revision
from b_lang.types import BError


RULE = 'fn free_entry(child: Bool, day: Text) -> Bool pure = child and day == "sat"\n'
SUNDAY = 'also free_entry(true, "sun")'


def load(source):
    namespace = {}
    exec(compile_b(source).code, namespace)
    return namespace


def test_protected_observables_survive_sequential_bookings_but_prices_change():
    base = (RULE
            + 'let one = 1\n'
            + 'fn seats(remaining: Int) -> Int pure = remaining - one\n'
            + 'fn recipient(account: Text) -> Text pure = account\n'
            + 'fn price(child: Bool, day: Text) -> Int pure = if free_entry(child, day) then 0 else 100\n')
    original = load(base)
    revised = load(base + SUNDAY + ' keeping seats, recipient')
    for namespace, expected_prices in ((original, [100, 100, 0]), (revised, [0, 100, 0])):
        remaining = 3
        receipts = []
        for child, day in ((True, "sun"), (False, "sun"), (True, "sat")):
            remaining = namespace["seats"](remaining)
            receipts.append((namespace["recipient"]("Ada"), namespace["price"](child, day)))
        assert remaining == 0
        assert receipts == [("Ada", price) for price in expected_prices]


def test_rule_extension_rejects_an_inherited_downstream_dependency_without_a_previous_file():
    base = (RULE
            + 'fn qty(child: Bool, day: Text) -> Int pure = if free_entry(child, day) then 2 else 1\n'
            + 'fn seats(child: Bool, day: Text) -> Int pure = qty(child, day)\n')
    assert load(base)["seats"](True, "sun") == 1
    assert load(base + SUNDAY)["seats"](True, "sun") == 2
    with pytest.raises(BError, match="seats -> qty -> free_entry"):
        compile_b(base + SUNDAY + " keeping seats")


def test_observable_tracks_dependencies_through_captured_scalar_bindings_even_in_dead_code():
    base = (RULE
            + 'let count = if true then 1 else if free_entry(true, "sun") then 2 else 1\n'
            + 'fn seats() -> Int pure = count\n')
    assert load(base)["seats"]() == load(base + SUNDAY)["seats"]() == 1
    with pytest.raises(BError, match="seats -> count -> free_entry"):
        compile_b(base + SUNDAY + " keeping seats")


@pytest.mark.parametrize(("declarations", "protected"), [
    ('', 'free_entry'),
    ('let seat_count = 1\n', 'seat_count'),
    ('', 'seets'),
    ('fn seats(n: Int) -> Int pure = n\n', 'seats, seats'),
    ('fn seats(n: Any) -> Int pure = 1\n', 'seats'),
    ('fn seats(n: List[Int]) -> Int pure = 1\n', 'seats'),
    ('use py:math as m\nfn seats(n: Float) -> Float = m.sqrt(n)\n', 'seats'),
])
def test_only_named_native_pure_scalar_observables_receive_preservation_guarantees(declarations, protected):
    with pytest.raises(BError) as error:
        compile_b(RULE + declarations + SUNDAY + ' keeping ' + protected)
    assert error.value.code == "E_KEEPING"


def test_keep_applies_to_the_named_function_at_equal_inputs():
    base = (RULE
            + 'fn reserve(qty: Int) -> Int pure = qty\n'
            + 'fn seats(child: Bool, day: Text) -> Int pure = reserve(if free_entry(child, day) then 2 else 1)\n')
    original = load(base)
    kept_helper = load(base + SUNDAY + ' keeping reserve')
    assert original["reserve"](1) == kept_helper["reserve"](1)
    assert original["seats"](True, "sun") != kept_helper["seats"](True, "sun")
    with pytest.raises(BError, match="seats -> free_entry"):
        compile_b(base + SUNDAY + ' keeping seats')


def test_pinned_reference_keeps_the_end_to_end_observable_when_candidate_edits_the_helper():
    base = (RULE
            + 'fn qty() -> Int pure = 1\n'
            + 'fn seats(remaining: Int) -> Int pure = remaining - qty()\n')
    delta = SUNDAY + ' keeping seats'
    candidate = base.replace('= 1\n', '= 2\n') + delta
    assert load(candidate)["seats"](4) == 2
    result = check_revision(base, candidate, delta)
    assert result["status"] == "counterexample"
    assert result["function"] == "qty"
    assert (result["expected"], result["actual"]) == (1, 2)


def test_pinned_reference_applies_keeping_even_if_the_candidate_inlines_the_rule():
    base = RULE + 'fn seats(child: Bool, day: Text) -> Int pure = if free_entry(child, day) then 2 else 1\n'
    candidate = base.replace('child and day == "sat"', 'child and (day == "sat" or day == "sun")')
    result = check_revision(base, candidate, SUNDAY + ' keeping seats')
    assert result["status"] == "invalid"
    assert "seats -> free_entry" in result["reason"]


@pytest.mark.parametrize("opaque", [
    'fn read(value: Any) -> Any pure = value.size\n',
    'fn same(value: List[Any]) -> Bool pure = value == value\n',
])
def test_structural_equality_cannot_certify_opaque_host_objects(opaque):
    base = RULE + opaque
    assert check_revision(base, base + SUNDAY, SUNDAY)["status"] == "unknown"


def test_property_reads_have_observable_host_behavior_despite_the_static_pure_annotation():
    reads = []

    class Counter:
        @property
        def size(self):
            reads.append(1)
            return len(reads)

    base = RULE + 'fn read(value: Any) -> Any pure = value.size\n'
    assert load(base)["read"](Counter()) == 1
    assert check_revision(base, base + SUNDAY, SUNDAY)["status"] == "unknown"
    assert reads == [1]
