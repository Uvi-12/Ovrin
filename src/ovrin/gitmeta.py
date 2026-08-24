"""Git facts about files. Everything here degrades gracefully, because we run
against dependency trees that are often not git repositories at all."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass
class FileGit:
    tracked: bool = False
    last_commit: str | None = None
    last_author: str | None = None
    last_date: str | None = None
    first_commit: str | None = None
    first_author: str | None = None


def _run(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, timeout=20, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


@lru_cache(maxsize=128)
def is_repo(root: Path) -> bool:
    return _run(root, "rev-parse", "--is-inside-work-tree") == "true"


@lru_cache(maxsize=128)
def tracked_files(root: Path) -> frozenset[str]:
    out = _run(root, "ls-files")
    return frozenset(out.splitlines()) if out else frozenset()


@lru_cache(maxsize=128)
def submodule_paths(root: Path) -> tuple[str, ...]:
    # Read .gitmodules directly so this works on a plain checkout where the
    # submodules were never initialised.
    gm = root / ".gitmodules"
    if not gm.is_file():
        return ()
    paths = []
    try:
        for line in gm.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("path"):
                _, _, value = line.partition("=")
                if value.strip():
                    paths.append(value.strip().rstrip("/"))
    except OSError:
        return ()
    return tuple(paths)


@lru_cache(maxsize=64)
def ignored(root: Path, candidates: tuple[str, ...]) -> frozenset[str]:
    # Ask git rather than reimplement gitignore. Getting ignore semantics
    # subtly wrong would corrupt the reachability column, which is the point of
    # the tool.
    if not candidates or not is_repo(root):
        return frozenset()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--stdin"],
            input="\n".join(candidates),
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    if proc.returncode > 1:   # 0 = some ignored, 1 = none, >1 = error
        return frozenset()
    return frozenset(line for line in proc.stdout.splitlines() if line)


def file_git(root: Path, rel: str) -> FileGit:
    if not is_repo(root):
        return FileGit()
    info = FileGit(tracked=rel in tracked_files(root))
    if not info.tracked:
        return info
    last = _run(root, "log", "-1", "--format=%H%x1f%an%x1f%aI", "--", rel)
    if last and len(parts := last.split("\x1f")) == 3:
        info.last_commit, info.last_author, info.last_date = parts
    first = _run(root, "log", "--reverse", "--format=%H%x1f%an", "--", rel)
    if first and (fl := first.splitlines()):
        p = fl[0].split("\x1f")
        info.first_commit = p[0]
        if len(p) > 1:
            info.first_author = p[1]
    return info


def introduced_in_authors_first_commit(root: Path, rel: str, author: str | None) -> bool | None:
    """True if the file's first commit is also that author's earliest commit to
    this repo. This is a git-history fact, not a pull-request fact: we do not
    claim it was the author's first PR, only their first observed commit here.
    Returns None when it cannot be decided."""
    if not author or not is_repo(root):
        return None
    fg = file_git(root, rel)
    if not fg.first_commit:
        return None
    author_first = _run(
        root, "log", "--reverse", "--author", author, "--format=%H"
    )
    if not author_first:
        return None
    return author_first.splitlines()[0] == fg.first_commit
