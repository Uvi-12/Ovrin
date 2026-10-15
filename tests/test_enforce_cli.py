"""Coverage for the `ovrin enforce` CLI and its SARIF output (the paper's centerpiece)."""
import json

from ovrin.cli import main


def test_enforce_json(repo, tmp_path):
    out = tmp_path / "e.json"
    rc = main(["enforce", str(repo), "--harness", "claude-code", "-f", "json", "-o", str(out)])
    assert rc in (0, 1)
    d = json.loads(out.read_text())
    assert set(d) >= {"harness", "summary", "decisions", "importDelegations"}
    assert d["harness"] == "claude-code"


def test_enforce_sarif(repo, tmp_path):
    out = tmp_path / "e.sarif"
    rc = main(["enforce", str(repo), "--harness", "claude-code", "-f", "sarif", "-o", str(out)])
    assert rc in (0, 1)
    raw = out.read_text()
    doc = json.loads(raw)
    assert doc["version"] == "2.1.0"
    driver = doc["runs"][0]["tool"]["driver"]
    assert driver["name"] == "ovrin"
    assert "github.com" in driver["informationUri"]
    assert "anonymous.4open" not in raw          # de-anonymization regression guard


def test_enforce_table(repo):
    assert main(["enforce", str(repo), "--harness", "codex-cli"]) in (0, 1)
