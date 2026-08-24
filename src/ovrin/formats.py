"""Load the instruction-format catalogue and match paths against it, honouring
each format's scope. Path position is the independent variable in this research,
so a format anchored to the repository root must not match the same filename
carried inside a dependency."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import yaml


@dataclass
class Format:
    family: str
    patterns: list[str]
    activation: str
    scope: str = "any-depth"      # repo-root | any-depth | anchored-subtree
    note: str = ""


def load(path: Path | None = None) -> list[Format]:
    if path is not None:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        text = resources.files("ovrin.data").joinpath("formats.yaml").read_text("utf-8")
        raw = yaml.safe_load(text)
    return [
        Format(
            family=f["family"],
            patterns=list(f["patterns"]),
            activation=f.get("activation", "unknown"),
            scope=f.get("scope", "any-depth"),
            note=(f.get("note") or "").strip(),
        )
        for f in raw.get("formats", [])
    ]


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Anchored-subtree glob: ** crosses directories, * does not."""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern[i:i + 2] == "**":
            if pattern[i:i + 3] == "**/":
                out.append("(?:.*/)?")
                i += 3
            else:
                out.append(".*")
                i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def matches(rel_path: str, pattern: str, scope: str) -> bool:
    name = Path(rel_path).name
    if scope == "repo-root":
        # The pattern is a concrete path from the repository root.
        return rel_path == pattern
    if scope == "any-depth":
        if "/" in pattern:
            return _glob_to_regex(pattern).match(rel_path) is not None
        return fnmatch.fnmatch(name, pattern)
    # anchored-subtree: the pattern is a path from root; match it exactly (with
    # glob semantics), never as a suffix inside a dependency.
    return _glob_to_regex(pattern).match(rel_path) is not None


def match_format(rel_path: str, formats: list[Format]) -> Format | None:
    # Most specific (longest matching pattern) wins.
    best: Format | None = None
    best_len = -1
    for fmt in formats:
        for pattern in fmt.patterns:
            if matches(rel_path, pattern, fmt.scope) and len(pattern) > best_len:
                best, best_len = fmt, len(pattern)
    return best
