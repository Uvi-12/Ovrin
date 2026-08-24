from pathlib import Path

from ovrin import gitmeta
from ovrin.harness import Rules
from ovrin.origin import classify


def _cl(repo, rel):
    r = Rules.load()
    return classify(repo, rel, r.vendor_markers,
                    gitmeta.tracked_files(repo), gitmeta.submodule_paths(repo))


def test_repo(repo: Path):
    assert _cl(repo, "AGENTS.md").cls == "repo"


def test_installed_dependency_when_ignored(repo: Path):
    # node_modules is git-ignored, so the file is installed, not committed.
    o = _cl(repo, "node_modules/left-pad/AGENTS.md")
    assert o.cls == "installed-dependency"
    assert o.package == "left-pad@1.3.0"


def test_vendored_when_committed(repo: Path):
    o = _cl(repo, "vendor/acme/CLAUDE.md")
    assert o.cls == "vendored"


def test_untracked(repo: Path):
    (repo / "STRAY.md").write_text("x")
    gitmeta.tracked_files.cache_clear()
    assert _cl(repo, "STRAY.md").cls == "untracked"
