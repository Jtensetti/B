import json

import pytest

from b_lang.cli import main
from b_lang.comment_migration import strip_comments
from b_lang.compiler import compile_b
from b_lang.types import BError


def test_hash_comments_are_rejected_except_as_text():
    for source in ("# note", "print 3 # note", 'fn f() -> Text = "#"# note'):
        with pytest.raises(BError) as error:
            compile_b(source)
        assert error.value.code == "E_SYNTAX"
    compile_b('assert "C#" == "C#"', strict=True)


def test_legacy_comments_preserve_escaped_strings_and_executable_tokens(capsys):
    values = ['C#', '"#inside"', 'slash\\', '\\\\"#', 'é# #', '\u2028#']
    statements = [f"print {json.dumps(value, ensure_ascii=False)}" for value in values]
    legacy = '\r\n'.join(statement + '# "discarded' for statement in statements)
    migrated = strip_comments(legacy)
    assert migrated == '\r\n'.join(statements)
    exec(compile_b(migrated, strict=True).code, {})
    assert capsys.readouterr().out == ''.join(value + '\n' for value in values)


def test_migration_is_lexical_for_incomplete_source_and_retains_physical_lines():
    source = '  # legacy\r\nprint "unterminated # keep\n# remove\rlet unfinished = # old'
    expected = '  \r\nprint "unterminated # keep\n\rlet unfinished = '
    assert strip_comments(source) == expected
    assert strip_comments(expected) == expected


def test_cli_migrates_to_stdout_and_leaves_the_input_alone(tmp_path, capsys):
    original = '# old file\r\nprint "C#" # display'
    path = tmp_path / 'legacy.b4'
    path.write_bytes(original.encode())
    assert main(['migrate-comments', str(path)]) == 0
    assert capsys.readouterr() == ('\r\nprint "C#" ', '')
    assert path.read_bytes() == original.encode()
