from pathlib import Path

from ovrin.discovery import scan
from ovrin.formats import load


def test_finds_all_formats(repo: Path):
    f = {x.rel_path for x in scan(repo, load())}
    assert {"AGENTS.md", "CLAUDE.md", ".cursorrules", "packages/api/AGENTS.md"} <= f


def test_descends_into_vendor_dirs(repo: Path):
    f = {x.rel_path for x in scan(repo, load())}
    assert "node_modules/left-pad/AGENTS.md" in f
    assert "vendor/acme/CLAUDE.md" in f


def test_activation_carried(repo: Path):
    conv = [x for x in scan(repo, load()) if x.rel_path == ".cursorrules"][0]
    assert conv.activation == "legacy"


def test_digest_complete_or_none(repo: Path):
    for x in scan(repo, load()):
        if x.digest_status == "complete":
            assert x.digest.startswith("sha256:")
        else:
            assert x.digest is None


def test_max_depth(repo: Path):
    f = {x.rel_path for x in scan(repo, load(), max_depth=0)}
    assert "AGENTS.md" in f and "packages/api/AGENTS.md" not in f
