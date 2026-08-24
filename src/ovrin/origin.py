"""Decide where an instruction file came from. This is the heart of the
supply-chain claim: a file the project wrote and reviews is a different artifact
from one that arrived inside a dependency, even when the bytes match."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import gitmeta


@dataclass
class Origin:
    cls: str
    container: str | None = None    # the vendor dir or submodule path
    package: str | None = None      # name@version where the ecosystem allows it
    evidence: list[str] = field(default_factory=list)


def _vendor_container(rel: str, markers: tuple[str, ...]) -> str | None:
    parts = rel.split("/")
    for i, part in enumerate(parts):
        if part in markers:
            return "/".join(parts[: i + 1])
    for marker in markers:               # multi-segment markers like go/pkg/mod
        if "/" in marker and (rel.startswith(marker + "/") or f"/{marker}/" in rel):
            idx = rel.find(marker)
            return rel[: idx + len(marker)]
    return None


def _npm_package(root: Path, container: str, rel: str) -> str | None:
    after = rel[len(container) + 1 :].split("/")
    if not after:
        return None
    if after[0].startswith("@") and len(after) > 1:
        name, pkg_dir = f"{after[0]}/{after[1]}", root / container / after[0] / after[1]
    else:
        name, pkg_dir = after[0], root / container / after[0]
    manifest = pkg_dir / "package.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8", errors="replace"))
            return f"{data.get('name', name)}@{data.get('version', 'unknown')}"
        except (OSError, json.JSONDecodeError):
            pass
    return name


def _has_workspaces(root: Path) -> bool:
    pkg = root / "package.json"
    if pkg.is_file():
        try:
            if json.loads(pkg.read_text(encoding="utf-8", errors="replace")).get("workspaces"):
                return True
        except (OSError, json.JSONDecodeError):
            pass
    return any((root / n).is_file() for n in ("pnpm-workspace.yaml", "go.work"))


def classify(
    root: Path, rel: str, markers: tuple[str, ...],
    tracked: frozenset[str], submodules: tuple[str, ...],
) -> Origin:
    # Order matters: submodule beats vendor-path beats tracked.
    for sm in submodules:
        if rel == sm or rel.startswith(sm + "/"):
            return Origin("submodule", container=sm, evidence=[".gitmodules entry"])

    container = _vendor_container(rel, markers)
    if container is not None:
        pkg = _npm_package(root, container, rel) if container.endswith("node_modules") else None
        # A vendored path that is tracked was committed; one that is not was
        # installed. That distinction matters for review, so we name both.
        cls = "vendored" if rel in tracked else "installed-dependency"
        return Origin(cls, container=container, package=pkg,
                      evidence=[f"under vendor directory '{container}'",
                                "tracked in git" if rel in tracked else "not tracked (installed)"])

    if rel in tracked:
        top = rel.split("/")[0]
        if "/" in rel and top in {"packages", "apps", "libs"} and _has_workspaces(root):
            return Origin("workspace", container=top, evidence=["workspace declaration present"])
        return Origin("repo", evidence=["tracked in git"])

    if gitmeta.is_repo(root):
        return Origin("untracked", evidence=["on disk, not in git ls-files"])
    return Origin("unknown", evidence=["not a git repository"])
