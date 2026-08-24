import json
from pathlib import Path

from ovrin.manifest import SCHEMA_VERSION, build
from ovrin.spdx import to_spdx


def test_shape(repo: Path):
    m = build(repo)
    assert m["schemaVersion"] == SCHEMA_VERSION
    assert m["summary"]["total"] == len(m["instructions"])


def test_third_party_counted(repo: Path):
    assert build(repo)["summary"]["thirdParty"] == 2


def test_ignored_file_not_claimed_loaded(repo: Path):
    e = next(x for x in build(repo)["instructions"] if "left-pad" in x["path"])
    assert e["gitIgnored"] is True
    assert "loaded" not in {r["verdict"] for r in e["reachability"].values()}


def test_ignored_file_not_review_enforced(repo: Path):
    # A catch-all '*' matches node_modules. That is not review.
    e = next(x for x in build(repo)["instructions"] if "left-pad" in x["path"])
    assert e["review"]["ruleMatches"] is True
    assert e["review"]["enforceable"] is False


def test_tracked_match_is_undecided(repo: Path):
    e = next(x for x in build(repo)["instructions"] if x["path"] == "AGENTS.md")
    assert e["review"]["enforceable"] is None


def test_no_timestamp_is_deterministic(repo: Path):
    a = build(repo, no_timestamp=True)
    b = build(repo, no_timestamp=True)
    assert json.dumps(a) == json.dumps(b)


def test_spdx_wellformed(repo: Path):
    d = to_spdx(build(repo))
    assert d["@context"].startswith("https://spdx.org/rdf/3.0")
    types = {n["type"] for n in d["@graph"]}
    assert {"software_File", "software_Sbom", "CreationInfo", "Tool"} <= types


def test_claude_code_absent_from_agents_md_reach(repo: Path):
    e = next(x for x in build(repo)["instructions"] if x["path"] == "AGENTS.md")
    assert "claude-code" not in e["reachability"]
