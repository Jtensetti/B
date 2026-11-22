import pytest

from b_lang.revisions import attach_delta, check_revision
from b_lang.types import BError


BOOKING = '''fn free(child: Bool, day: Text) -> Bool pure = child and day == "sat"
fn seats(child: Bool, day: Text) -> Int pure = 1
fn fee(child: Bool, day: Text) -> Int pure = if free(child, day) then 0 else 100
'''
SUNDAY = 'also free(true, "sun") keeping seats'
MONDAY = 'also free(true, "mon") keeping seats'


def test_one_declaration_is_the_executable_change_and_the_pinned_frame():
    candidate = attach_delta(BOOKING, SUNDAY)
    for pinned, authority in ((None, "candidate"), (SUNDAY, "pinned")):
        result = check_revision(BOOKING, candidate, pinned)
        assert result["status"] == "proved"
        assert result["method"] == "identical-bir"
        assert result["authority"] == authority
        assert result["delta"] == [SUNDAY]


def test_failure_to_apply_a_pinned_change_has_a_concrete_witness():
    result = check_revision(BOOKING, BOOKING, SUNDAY)
    assert result["status"] == "counterexample"
    assert result["function"] == "free"
    assert result["arguments"] == {"child": True, "day": "sun"}
    assert result["expected"] is True and result["actual"] is False


def test_alternative_syntax_can_establish_the_whole_pinned_change():
    rewritten = BOOKING.replace('day == "sat"', '(day == "sat" or day == "sun")')
    result = check_revision(BOOKING, rewritten, SUNDAY)
    assert result["status"] == "proved"
    assert result["method"] == "exhaustive-scalar-classes"
    assert result["cases"] > 0


def test_reference_includes_earlier_accepted_changes():
    accepted = attach_delta(BOOKING, SUNDAY)
    candidate = attach_delta(accepted, MONDAY)
    assert check_revision(accepted, candidate)["delta"] == [MONDAY]
    assert check_revision(accepted, candidate, MONDAY)["status"] == "proved"
    assert check_revision(accepted, attach_delta(BOOKING, MONDAY), MONDAY)["status"] == "invalid"


def test_no_op_new_fact_and_missing_inferred_authorization_are_invalid():
    saturday = 'also free(true, "sat")'
    result = check_revision(BOOKING, attach_delta(BOOKING, saturday))
    assert result["status"] == "invalid"
    assert "already true" in result["reason"]
    assert check_revision(BOOKING, BOOKING)["status"] == "invalid"


def test_pinned_change_cannot_be_broadened_by_explicit_declaration():
    result = check_revision(BOOKING, attach_delta(BOOKING, SUNDAY + "\n" + MONDAY), SUNDAY)
    assert result["status"] == "invalid"
    assert "outside the pinned delta" in result["reason"]


def test_one_extended_rule_protects_seats_from_itself_in_a_multi_rule_program():
    base = '''fn free(child: Bool) -> Bool pure = false
fn extra(child: Bool) -> Bool pure = false
fn seats(child: Bool) -> Int pure = if extra(child) then 2 else 1
'''
    delta = 'also free(true) keeping seats\nalso extra(true)'
    result = check_revision(base, attach_delta(base, delta), delta)
    assert result["status"] == "proved"
    conflict = delta + ' keeping seats'
    assert check_revision(base, attach_delta(base, conflict), conflict)["status"] == "invalid"


def test_pinned_keeping_survives_omission_of_declaration_in_equivalent_code():
    candidate = BOOKING.replace('day == "sat"', '(day == "sat" or day == "sun")')
    candidate = candidate.replace('Int pure = 1', 'Int pure = if free(child, day) then 1 else 1')
    result = check_revision(BOOKING, candidate, SUNDAY)
    assert result["status"] == "invalid"
    assert "E_KEEPING" in result["reason"]


def test_unbounded_integer_equations_do_not_get_proof_from_finite_samples():
    base = BOOKING + 'fn twice(n: Int) -> Int pure = n * 2\n'
    candidate = attach_delta(base.replace("n * 2", "n + n"), SUNDAY)
    assert check_revision(base, candidate, SUNDAY)["status"] == "unknown"


@pytest.mark.parametrize('delta', ['print 123', '', 'also free(true, "sun")\nprint 123'])
def test_delta_rejects_any_command_other_than_a_declaration(delta):
    with pytest.raises(BError):
        attach_delta(BOOKING, delta)


def test_contracts_and_public_signatures_remain_part_of_the_frame():
    base = BOOKING + 'fn area(n: Int) -> Int pure requires n > 0 = n * n\n'
    for changed in ('requires n >= 0', ''):
        candidate = attach_delta(base.replace('requires n > 0', changed), SUNDAY)
        assert check_revision(base, candidate, SUNDAY)["status"] == "invalid"
    renamed = BOOKING.replace('fn seats(child: Bool', 'fn seats(visitor: Bool')
    assert check_revision(BOOKING, attach_delta(renamed, SUNDAY), SUNDAY)["status"] == "invalid"


def _run_stdout(source, capsys):
    from b_lang.compiler import compile_b

    exec(compile_b(source).code, {})
    return capsys.readouterr().out


def test_runnable_booking_has_one_frozen_frame_for_functions_and_console(capsys):
    base = ('permit [console]\n' + BOOKING
            + 'fn recipient(account: Text) -> Text pure = account\n'
            + 'print fee(true, "sun")\nprint recipient("Ada")\n')
    delta = SUNDAY + ', recipient'
    candidate = attach_delta(base, delta)
    assert check_revision(base, candidate, delta)["prints"] == 2
    wrong = candidate.replace('print recipient("Ada")', 'print recipient("Bo")')
    result = check_revision(base, wrong, delta)
    assert result["status"] == "counterexample"
    assert result["output_index"] == 2
    assert result["method"] == "native-output-stream"
    assert capsys.readouterr().out == ""
    assert result["expected"] == _run_stdout(candidate, capsys) == "0\nAda\n"
    assert result["actual"] == _run_stdout(wrong, capsys) == "0\nBo\n"


@pytest.mark.parametrize('edits', [
    ('print 1\nprint "two"', 'print "1"\nprint "two"'),
    ('print "a\\nb"\nprint "c"', 'print "a"\nprint "b\\nc"'),
])
def test_distinct_print_expressions_can_render_the_same_stream(edits, capsys):
    before, after = edits
    base = BOOKING + before
    candidate = attach_delta(BOOKING + after, SUNDAY)
    result = check_revision(base, candidate, SUNDAY)
    assert result["status"] == "proved"
    assert result["output_method"] == "native-output-stream"
    assert _run_stdout(attach_delta(base, SUNDAY), capsys) == _run_stdout(candidate, capsys)


def test_signed_zero_remains_visible_in_rendered_outputs(capsys):
    base = BOOKING + 'print 0.0\n'
    candidate = attach_delta(base.replace('print 0.0', 'print -0.0'), SUNDAY)
    result = check_revision(base, candidate, SUNDAY)
    assert result["status"] == "counterexample"
    assert result["expected"] == _run_stdout(attach_delta(base, SUNDAY), capsys) == '0.0\n'
    assert result["actual"] == _run_stdout(candidate, capsys) == '-0.0\n'


def test_fail_closed_before_emitting_unreachable_stdout_witness():
    base = (BOOKING + 'fn portion(n: Int) -> Int pure = 10 % n\n'
            + 'print portion(0)\nprint "Ada"')
    candidate = attach_delta(base.replace('print "Ada"', 'print "Bo"'), SUNDAY)
    result = check_revision(base, candidate, SUNDAY)
    assert result["status"] == "unknown"
    assert "print 1" in result["reason"]


def test_extra_print_is_a_structural_change_to_output_interface():
    candidate = attach_delta(BOOKING + 'print "extra"\n', SUNDAY)
    result = check_revision(BOOKING, candidate, SUNDAY)
    assert result["status"] == "invalid"
    assert "number of print sites" in result["reason"]


@pytest.mark.parametrize('extra', [
    'use py:math as m\nprint m.sqrt(2.0)',
    'print if true then true else [1] == [1]',
    'permit [foreign]\n'
])
def test_opaque_or_foreign_print_never_receives_structural_proof(extra):
    base = extra + '\n' + BOOKING if extra.startswith('permit') else BOOKING + extra
    assert check_revision(base, attach_delta(base, SUNDAY), SUNDAY)["status"] != "proved"


def test_first_error_precedes_later_opaque_output():
    base = BOOKING + 'fn fraction(n: Int) -> Int pure = 4 % n\nprint "Ada"\nprint fraction(0)'
    candidate = attach_delta(base.replace('print "Ada"', 'print "Bo"'), SUNDAY)
    result = check_revision(base, candidate, SUNDAY)
    assert result["status"] == "counterexample"
    assert result["expected"] == "Ada\n" and result["actual"] == "Bo\n"


def test_console_permission_is_compared_even_for_identical_successful_output():
    base = BOOKING + 'print fee(true, "sun")\n'
    result = check_revision(base, attach_delta('permit [console]\n' + base, SUNDAY), SUNDAY)
    assert result["status"] == "invalid"
    assert "permissions" in result["reason"]


def test_each_simultaneous_ground_fact_is_measured_against_the_frozen_old_rule():
    base = ('fn member(x: Bool) -> Bool pure = false\n'
            'fn reduced(x: Bool) -> Bool pure = member(x)\n'
            'print reduced(true)\n')
    delta = 'also member(true)\nalso reduced(true)'
    assert check_revision(base, attach_delta(base, delta), delta)["status"] == "proved"
    already = base.replace('= member(x)', '= not member(x)')
    result = check_revision(already, attach_delta(already, delta), delta)
    assert result["status"] == "invalid"
    assert "already true in the accepted base" in result["reason"]
