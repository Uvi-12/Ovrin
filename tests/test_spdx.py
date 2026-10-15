"""Coverage for the SPDX 3.0-aligned exporter (a README headline, previously untested)."""
import json

from ovrin.cli import main
from ovrin.harness import Rules
from ovrin.manifest import build
from ovrin.spdx import to_spdx


def test_to_spdx_structure(repo):
    m = build(repo, Rules.load(), no_timestamp=True)
    doc = to_spdx(m, name=repo.name)
    assert doc["@context"].startswith("https://spdx.org/rdf/3.0")
    graph = doc["@graph"]
    files = [n for n in graph if n.get("type") == "software_File"]
    assert files, "expected software_File nodes"
    assert all(n.get("spdxId") and n.get("name") for n in files)
    sbom = [n for n in graph if n.get("type") == "software_Sbom"]
    assert len(sbom) == 1
    ids = {n.get("spdxId") for n in graph}
    assert set(sbom[0]["rootElement"]) <= ids
    for n in files:
        for h in n.get("verifiedUsing", []):
            assert h["algorithm"] == "sha256"
            assert len(h["hashValue"]) == 64          # complete digest, never partial


def test_cli_scan_spdx(repo, tmp_path):
    out = tmp_path / "o.spdx.json"
    rc = main(["scan", str(repo), "-f", "spdx", "--no-timestamp", "-o", str(out)])
    assert rc == 0
    doc = json.loads(out.read_text())
    assert "@graph" in doc and doc["@context"]
