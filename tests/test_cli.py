import json
from pathlib import Path

from ovrin.cli import main


def test_table(repo: Path, capsys):
    assert main(["scan", str(repo), "--no-color"]) == 0
    assert "instruction manifest" in capsys.readouterr().out


def test_json(repo: Path, capsys):
    assert main(["scan", str(repo), "-f", "json"]) == 0
    json.loads(capsys.readouterr().out)


def test_fail_on_third_party(repo: Path):
    assert main(["scan", str(repo), "--fail-on-third-party", "--no-color"]) == 1


def test_clean_repo_passes(tmp_path: Path):
    (tmp_path / "README.md").write_text("nothing")
    assert main(["scan", str(tmp_path), "--fail-on-third-party", "--no-color"]) == 0


def test_bad_path():
    assert main(["scan", "/nope/xyz"]) == 2


def test_harnesses(capsys):
    assert main(["harnesses"]) == 0
    out = capsys.readouterr().out
    assert "per behavioural claim" in out
    assert "override_semantics" in out  # per-claim rows are shown
