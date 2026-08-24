"""CODEOWNERS parsing and matching, following GitHub's documented semantics.

The rules that matter for correctness:
- Last matching rule wins.
- A pattern with no slash (except a trailing one) matches at any depth.
- A leading slash anchors to the repository root.
- A trailing slash matches a directory and everything under it.
- `*` matches anything except a slash. It does not cross directory boundaries,
  so `docs/*` matches `docs/a.md` but not `docs/build/a.md`.
- `**` matches across directory boundaries.

This matcher is the headline number's denominator logic, so it is tested
against GitHub's own published examples in tests/test_codeowners.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# GitHub looks in these locations, in order, and uses the first found.
LOCATIONS = (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")


@dataclass(frozen=True)
class Rule:
    pattern: str
    owners: tuple[str, ...]
    line: int


def find(root: Path) -> Path | None:
    for rel in LOCATIONS:
        if (root / rel).is_file():
            return root / rel
    return None


def parse(text: str) -> list[Rule]:
    rules = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        rules.append(Rule(parts[0], tuple(parts[1:]), n))
    return rules


def _compile(pattern: str) -> re.Pattern[str]:
    """Translate a CODEOWNERS pattern to a regex over a repo-relative path,
    following GitHub's gitignore-style semantics."""
    anchored = pattern.startswith("/")
    dir_only = pattern.endswith("/")
    core = pattern.strip("/")

    # Build the regex token by token so * and ** differ.
    out: list[str] = []
    i = 0
    while i < len(core):
        ch = core[i]
        if core[i:i + 2] == "**":
            # ** matches across directories. Consume an optional following slash.
            if core[i:i + 3] == "**/":
                out.append("(?:.*/)?")
                i += 3
            else:
                out.append(".*")
                i += 2
        elif ch == "*":
            out.append("[^/]*")   # does not cross a directory boundary
            i += 1
        elif ch == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    body = "".join(out)

    prefix = "" if anchored else r"(?:.*/)?"
    ends_wild = core.endswith("*")   # e.g. docs/* or *.js
    if dir_only:
        # A directory pattern matches the directory and everything beneath it.
        suffix = r"/.*"
    elif ends_wild:
        # A pattern ending in * matches within the current directory only.
        # docs/* matches docs/a.md, not docs/build/a.md. The trailing wildcard
        # already consumed this segment, so no directory suffix is added.
        suffix = r""
    elif core and "/" not in core:
        # A bare filename with no slash matches at any depth, as a file or as a
        # directory prefix (GitHub treats `foo` like `foo` and `foo/**`).
        suffix = r"(?:/.*)?"
    else:
        # A path with slashes that names a concrete path matches that path, and
        # everything under it if it is a directory.
        suffix = r"(?:/.*)?"
    return re.compile(f"^{prefix}{body}{suffix}$")


class Owners:
    def __init__(self, rules: list[Rule], source: str | None) -> None:
        self.rules = rules
        self.source = source
        self._compiled = [(r, _compile(r.pattern)) for r in rules]

    @classmethod
    def load(cls, root: Path) -> Owners:
        path = find(root)
        if path is None:
            return cls([], None)
        try:
            return cls(parse(path.read_text(encoding="utf-8", errors="replace")),
                       str(path.relative_to(root)))
        except OSError:
            return cls([], None)

    @property
    def present(self) -> bool:
        return self.source is not None

    def match(self, rel: str) -> Rule | None:
        """Return the last rule that matches, or None. GitHub is last-match-wins."""
        found = None
        for rule, rx in self._compiled:
            if rx.match(rel):
                found = rule
        return found

    def owners_for(self, rel: str) -> tuple[str, ...]:
        r = self.match(rel)
        return r.owners if r else ()
