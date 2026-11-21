"""Coverage numbers must reveal limitations rather than call every import verified."""
import json
from pathlib import Path

import pytest

from b_lang.audit import audit_python
from b_lang.cli import main


def test_audit_known_declared_functions():
    result = audit_python('b_examples.demo_lib').to_dict()
    assert result['public_direct_functions'] == 3
    assert result['static_signatures'] == 3
    assert result['public_direct_coverage'] == 1.0
    assert result['external_implementations_verified'] is False
    assert result['analysis_complete_for_public_api'] is False


def test_audit_reports_reexports_without_inflating_coverage(tmp_path, monkeypatch):
    (tmp_path / 'b_audit_fixtures.py').write_text('''from math import sqrt as my_sqrt
from statistics import *
def typed(value: int) -> int: return value
class Widget:
    def operation(self, x: int) -> int: return x
''')
    monkeypatch.syspath_prepend(str(tmp_path))
    result = audit_python('b_audit_fixtures').to_dict()
    assert result['static_signatures'] == 1
    assert result['public_direct_functions'] == 1
    assert result['named_reexports'] == 1
    assert result['star_reexports'] == 1
    assert result['public_classes'] == 1
    assert result['analysis_complete_for_public_api'] is False


def test_audit_json_output(capsys):
    assert main(['audit', 'py:b_examples.demo_lib', '--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['target'] == 'py:b_examples.demo_lib'
    assert 'parent_package_initializers_may_execute' in result


def test_audit_large_library_if_installed():
    pytest.importorskip('numpy')
    result = audit_python('numpy').to_dict()
    assert result['target'] == 'py:numpy'
    assert result['static_signatures'] <= result['public_direct_functions']
    assert not result['analysis_complete_for_public_api']
    assert result['named_reexports'] > 50
