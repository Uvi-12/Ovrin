"""End-to-end regression: a REAL manifest entry (package as a 'name@version'
string, the shape origin.py actually emits) must map to a pkg: purl so policy
rules can match. The unit tests hand-built dicts and missed this."""
from ovrin.delegation import manifest_entry_to_source
from ovrin.harness import Rules
from ovrin.manifest import build


def test_real_manifest_npm_entry_maps_to_purl(repo):
    m = build(repo, Rules.load(), no_timestamp=True)
    npm = [e for e in m["instructions"] if "node_modules/left-pad" in e["path"]]
    assert npm, "fixture should carry an installed-dependency instruction file"
    src = manifest_entry_to_source(npm[0])
    assert src.startswith("pkg:npm/left-pad"), src
    assert not src.startswith("unknown:"), "delegation package mapping regressed"
