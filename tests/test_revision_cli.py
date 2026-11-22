import json

from b_lang.cli import main


BASE = 'fn free(child: Bool, day: Text) -> Bool pure = child and day == "sat"\n'
DELTA = 'also free(true, "sun")\n'


def test_run_build_and_check_with_one_delta(tmp_path, capsys):
    before, delta = tmp_path / "old.bee", tmp_path / "extra.bee"
    before.write_text(BASE + 'print free(true, "sun")\nprint free(false, "sun")')
    delta.write_text(DELTA)
    argv = [str(before), "--with", str(delta)]
    assert main(["check", *argv, "--strict", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "accepted"
    assert main(["run", *argv]) == 0
    assert capsys.readouterr().out.splitlines() == ["True", "False"]
    assert main(["build", *argv]) == 0
    exec(capsys.readouterr().out, {})
    assert capsys.readouterr().out.splitlines() == ["True", "False"]
    delta.write_text("print 77")
    assert main(["run", *argv]) == 1
    assert "77" not in capsys.readouterr().out


def test_revision_cli_exit_and_counterexample(tmp_path, capsys):
    before, after, delta = (tmp_path / f"{name}.bee" for name in ("old", "new", "delta"))
    before.write_text(BASE)
    delta.write_text(DELTA)
    after.write_text(BASE + DELTA)
    argv = ["revision", str(before), str(after), "--delta", str(delta)]
    assert main(argv) == 0
    assert "proved" in capsys.readouterr().out
    after.write_text(BASE)
    assert main(argv + ["--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["arguments"] == {"child": True, "day": "sun"}
    assert main(argv) == 1
    assert "sun" in capsys.readouterr().out
    delta.unlink()
    assert main(argv + ["--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "invalid"


def test_console_witness_visible_on_command_line(tmp_path, capsys):
    before, after, delta = (tmp_path / f"{name}.bee" for name in ("old", "new", "delta"))
    before.write_text(BASE + 'print "buyer"\n')
    after.write_text(BASE + 'print "guest"\n' + DELTA)
    delta.write_text(DELTA)
    assert main(["revision", str(before), str(after), "--delta", str(delta)]) == 1
    output = capsys.readouterr().out
    assert "print 1" in output and "buyer" in output and "guest" in output
