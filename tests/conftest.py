import subprocess
from pathlib import Path

import pytest


def _git(r: Path, *a: str) -> None:
    subprocess.run(["git", "-C", str(r), *a], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "proj"
    for d in ("packages/api", "node_modules/left-pad", "vendor/acme", ".github"):
        (r / d).mkdir(parents=True, exist_ok=True)
    (r / "AGENTS.md").write_text("Run make test.\n")
    (r / "CLAUDE.md").write_text("Build with make.\n")
    (r / ".cursorrules").write_text("tabs\n")
    (r / "packages/api/AGENTS.md").write_text("shared client\n")
    (r / "node_modules/left-pad/AGENTS.md").write_text("canary-npm\n")
    (r / "node_modules/left-pad/package.json").write_text('{"name":"left-pad","version":"1.3.0"}\n')
    (r / "vendor/acme/CLAUDE.md").write_text("canary-vendor\n")
    (r / ".gitignore").write_text("node_modules/\n")
    (r / ".github/CODEOWNERS").write_text("*  @org/maintainers\nAGENTS.md  @org/platform\n")
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "a@b.c")
    _git(r, "config", "user.name", "t")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "init")
    return r
