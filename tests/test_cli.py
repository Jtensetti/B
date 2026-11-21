import json
from pathlib import Path
from b_lang.cli import main


def test_bsrc_is_preferred_source_and_check_json(tmp_path: Path, capsys):
    example = tmp_path / 'hello.bsrc'
    example.write_text('print if true then 42 else 13\n', encoding='utf-8')
    assert main(['check', str(example), '--strict', '--json']) == 0
    record = json.loads(capsys.readouterr().out)
    assert record['status'] == 'accepted'
    assert record['spec'] == '0.5'
    assert record['diagnostics'] == []
    assert record['behavior_proven'] is False


def test_old_b_extension_remains_supported(tmp_path: Path, capsys):
    example = tmp_path / 'legacy.b'
    example.write_text('print 42\n', encoding='utf-8')
    assert main(['run', str(example)]) == 0
    assert capsys.readouterr().out.strip() == '42'


def test_reject_unrelated_extensions(tmp_path: Path, capsys):
    example = tmp_path / 'not_b.py'
    example.write_text('print 42\n', encoding='utf-8')
    assert main(['check', str(example), '--json']) == 1
    record = json.loads(capsys.readouterr().out)
    assert record['error']['code'] == 'E_EXTENSION'


def test_json_error_is_machine_readable(tmp_path: Path, capsys):
    example = tmp_path / 'fail.bsrc'
    example.write_text('let n: Int = "bad"\n', encoding='utf-8')
    assert main(['check', str(example), '--json']) == 1
    record = json.loads(capsys.readouterr().out)
    assert record['status'] == 'rejected'
    assert record['error']['code'] == 'E_TYPE'


def test_json_contracts_report_trusted_assumptions(tmp_path: Path, capsys):
    example = tmp_path / 'contract.bsrc'
    example.write_text('use py:statistics as stats\nforeign stats.median(List[Float]) -> Float\nprint stats.median([1,2,3])', encoding='utf-8')
    assert main(['check', str(example), '--strict', '--json']) == 0
    record = json.loads(capsys.readouterr().out)
    assert record['assumed_foreign_contracts'] == ['py:statistics.median(List[Float]) -> Float']


def test_strict_json_rejection_includes_diagnostic_details(tmp_path: Path, capsys):
    path = tmp_path / 'untyped.bsrc'
    path.write_text('use py:json as json\nprint json.dumps([1,2,3])', encoding='utf-8')
    assert main(['check', str(path), '--strict', '--json']) == 1
    obj = json.loads(capsys.readouterr().out)
    assert obj['error']['code'] == 'E_STRICT'
    assert any(d['code'] == 'W_UNCHECKED_FOREIGN' for d in obj['diagnostics'])
