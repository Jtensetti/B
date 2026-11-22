from io import StringIO

import pytest

from b_lang.cli import main


ROUTE = 'fn route(days: Int) -> Text pure = if days < 3 then "priority" else "standard"'
OTHER = 'fn other(kind: Int, count: Int) -> Int pure = kind + count'
SOURCE = f'{ROUTE}\n{OTHER}\nprint route(5)\nprint other(5, 5)\n'
ROWS = 'route 5 "express med #5"\nother count 5 9\n'
NOTES = ('next route when days == 5 => "express med #5"',
         'next other when count == 5 => 9')


def test_file_and_stdin_preview_and_show_target_context(tmp_path, capsys, monkeypatch):
    path = tmp_path / "program.bee"
    path.write_text(SOURCE)
    rows = tmp_path / "edits.short"
    rows.write_text(ROWS)
    assert main(["next", str(path), "--from-short", str(rows)]) == 0
    assert capsys.readouterr().out == "\n".join([*NOTES, ""])
    monkeypatch.setattr("sys.stdin", StringIO(ROWS))
    assert main(["next", str(path), "--context", "--from-short", "-"]) == 0
    assert capsys.readouterr().out == "\n".join([ROUTE, NOTES[0], OTHER, NOTES[1], ""])
    assert path.read_text() == SOURCE


@pytest.mark.parametrize("ending, trailing", [("\r\n", True), ("\n", False), ("\r", False)])
def test_batch_changes_behavior_and_preserves_original_line_endings(tmp_path, capsys, monkeypatch, ending, trailing):
    path = tmp_path / "program.bee"
    def encoded(text):
        if not trailing:
            text = text.removesuffix("\n")
        return text.replace("\n", ending).encode("utf-8")
    path.write_bytes(encoded(SOURCE))
    monkeypatch.setattr("sys.stdin", StringIO(ROWS))
    assert main(["next", str(path), "--from-short", "-", "--apply", "--strict"]) == 0
    assert not capsys.readouterr().out
    expected = SOURCE.replace('= if days', '= if days == 5 then "express med #5" else if days')
    expected = expected.replace("= kind + count", "= if count == 5 then 9 else kind + count")
    assert path.read_bytes() == encoded(expected)
    assert main(["run", str(path)]) == 0
    assert capsys.readouterr().out == "express med #5\n9\n"


def test_error_on_later_row_cannot_partially_apply_a_batch(tmp_path, capsys, monkeypatch):
    path = tmp_path / "program.bee"
    path.write_text(SOURCE)
    monkeypatch.setattr("sys.stdin", StringIO('route 5 "express"\nother 5 9\n'))
    assert main(["next", str(path), "--from-short", "-", "--apply"]) == 1
    out, err = capsys.readouterr()
    assert out == "" and "other" in err and "count" in err
    assert path.read_text() == SOURCE


def test_pending_from_source_never_applied_by_external_rows(tmp_path, capsys, monkeypatch):
    path = tmp_path / "program.bee"
    original = SOURCE + NOTES[0] + "\n"
    path.write_text(original)
    for rows, expected_status in [("", 0), (" \n\t", 0), ("other count 5 9\n", 1)]:
        monkeypatch.setattr("sys.stdin", StringIO(rows))
        assert main(["next", str(path), "--from-short", "-", "--apply"]) == expected_status
        out, err = capsys.readouterr()
        assert out == ""
        if expected_status:
            assert "E_SHORTHAND_PENDING" in err
        assert path.read_text() == original


def test_unreadable_rows_do_not_touch_the_program(tmp_path, capsys):
    path = tmp_path / "program.bee"
    path.write_text(SOURCE)
    rows = tmp_path / "missing.short"
    assert main(["next", str(path), "--from-short", str(rows), "--apply"]) == 1
    out, err = capsys.readouterr()
    assert out == "" and str(rows) in err
    assert path.read_text() == SOURCE


def test_replaying_an_external_batch_does_not_repeat_the_branches(tmp_path, capsys):
    path = tmp_path / "program.bee"
    path.write_text(SOURCE)
    rows = tmp_path / "repeat.short"
    rows.write_text(ROWS)
    command = ["next", str(path), "--from-short", str(rows), "--apply"]
    assert main(command) == 0
    first = path.read_bytes()
    stat = path.stat()
    assert main(command) == 0
    assert capsys.readouterr().out == ""
    assert path.read_bytes() == first
    assert (path.stat().st_mtime_ns, path.stat().st_ino) == (stat.st_mtime_ns, stat.st_ino)


def test_strict_preview_and_apply_reject_changed_contract(tmp_path, capsys, monkeypatch):
    path = tmp_path / "program.bee"
    original = "fn mark(x: Int) -> Int pure ensures result > 0 = 1\n"
    path.write_text(original)
    for action in [[], ["--apply"]]:
        monkeypatch.setattr("sys.stdin", StringIO("mark 1 -2\n"))
        assert main(["next", str(path), "--from-short", "-", "--strict", *action]) == 1
        out, err = capsys.readouterr()
        assert out == "" and "E_STRICT" in err
        assert path.read_text() == original
