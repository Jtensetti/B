import json
import os
import stat

import pytest

from b_lang import handoff_cli
from b_lang.cli import main


SOURCE = ('fn label(n: Int) -> Text pure = "räv"\n'
          'next label when n == 1 => "röd"\n'
          'print label(1)\n')


def test_list_apply_and_repeat_through_normal_entry_points(tmp_path, capsys):
    path = tmp_path / "labels.bee"
    before = SOURCE.replace("\n", "\r\n").encode()
    path.write_bytes(before)
    path.chmod(0o740)
    assert main(["next", str(path)]) == 0
    assert capsys.readouterr().out == 'next label when n == 1 => "röd"\n'
    assert path.read_bytes() == before
    assert main(["run", str(path)]) == 0
    assert capsys.readouterr().out == "räv\n"

    assert main(["next", str(path), "--apply", "--strict"]) == 0
    assert capsys.readouterr().out == ""
    revised = path.read_bytes()
    assert b"next label" not in revised
    assert b"\r\n" in revised and b"\n" not in revised.replace(b"\r\n", b"")
    assert stat.S_IMODE(path.stat().st_mode) == 0o740
    assert main(["run", str(path)]) == 0
    assert capsys.readouterr().out == "röd\n"

    original_file = path.stat()
    assert main(["next", str(path)]) == 0
    assert main(["next", str(path), "--apply"]) == 0
    assert capsys.readouterr().out == ""
    assert path.read_bytes() == revised
    assert path.stat().st_mtime_ns == original_file.st_mtime_ns
    assert path.stat().st_ino == original_file.st_ino


def test_failed_check_preserves_invalid_source_and_prints_no_instruction(tmp_path, capsys):
    path = tmp_path / "labels.bee"
    source = SOURCE.replace('=> "röd"', "=> 7")
    path.write_text(source, encoding="utf-8")
    for action in ([], ["--apply"]):
        assert main(["next", str(path), *action]) == 1
        out, err = capsys.readouterr()
        assert not out
        assert "B next:" in err
        assert path.read_text(encoding="utf-8") == source


def test_file_changed_after_validation_is_not_overwritten(tmp_path, capsys, monkeypatch):
    from b_lang import handoff
    path = tmp_path / "concurrent.bee"
    path.write_text(SOURCE, encoding="utf-8")
    inspect = handoff.inspect_handoff
    competing_source = 'print "edited while checking"\n'

    def change_file_while_checking(source, **kwargs):
        result = inspect(source, **kwargs)
        path.write_text(competing_source)
        return result

    monkeypatch.setattr(handoff, "inspect_handoff", change_file_while_checking)
    assert main(["next", str(path), "--apply"]) == 1
    assert "E_HANDOFF_CHANGED" in capsys.readouterr().err
    assert path.read_text() == competing_source
    assert list(tmp_path.iterdir()) == [path]


def test_replace_error_leaves_source_intact(tmp_path, capsys, monkeypatch):
    path = tmp_path / "labels.bee"
    path.write_text(SOURCE, encoding="utf-8")

    def interrupted(stage, target):
        raise OSError("simulated rename error")

    monkeypatch.setattr(handoff_cli.os, "replace", interrupted)
    assert main(["next", str(path), "--apply"]) == 1
    assert "simulated rename error" in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == SOURCE
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.skipif(os.name == "nt", reason="Creating symlinks on Windows depends on host permissions")
def test_apply_through_a_symlink_updates_its_target(tmp_path, capsys):
    target = tmp_path / "real-source"
    target.write_text(SOURCE, encoding="utf-8")
    link = tmp_path / "entry.bee"
    link.symlink_to(target.name)
    assert main(["next", str(link), "--apply"]) == 0
    assert link.is_symlink()
    assert main(["run", str(link)]) == 0
    assert capsys.readouterr().out == "röd\n"


def test_requested_proofs_also_cover_the_pending_revision(tmp_path, capsys):
    path = tmp_path / "pending-divisor.bee"
    path.write_text("fn ratio(x: Int, y: Int) -> Float pure = 1.0\nnext ratio when x == 1 => 1 / y\n")
    assert main(["check", str(path), "--require-proofs", "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["error"]["code"] == "E_PROOF_REQUIRED"
    assert "pending" in result["error"]["message"]
    assert any(row["status"] != "proved" for row in result["pending_analysis"]["obligations"])
    assert not any(row["status"] != "proved" for row in result["contract_analysis"]["obligations"])


def test_strict_apply_leaves_an_unproved_future_contract_for_review(tmp_path, capsys):
    path = tmp_path / "pending-contract.bee"
    source = ("fn square(x: Int, y: Int) -> Int pure ensures result >= 0 = 2\n"
              "next square when x == 1 => y * y\n")
    path.write_text(source)
    assert main(["next", str(path), "--apply", "--strict"]) == 1
    assert "E_STRICT" in capsys.readouterr().err
    assert path.read_text() == source
    assert main(["check", str(path), "--strict", "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert any("Pending handoff" in warning["message"] for warning in result["diagnostics"])


def test_context_lists_only_target_and_instruction_once_in_instruction_order(tmp_path, capsys):
    path = tmp_path / "target.bee"
    first = "fn first(x: Int) -> Int pure = cases x {\n == 5 => 9\n else => x\n}"
    other = "fn untouched(x: Int) -> Int = x"
    last = "fn last(x: Int) -> Int pure = x - 1"
    last_note = "next last when x == 1 => 2"
    first_note = "next first when x == 2 => 5"
    source = "\n".join([last_note, first, other, last, first_note])
    path.write_text(source)
    assert main(["next", str(path), "--context"]) == 0
    assert capsys.readouterr().out == "\n".join([last, last_note, first, first_note, ""])
    assert path.read_text() == source
