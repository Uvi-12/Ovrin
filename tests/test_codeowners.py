"""CODEOWNERS matching, pinned to GitHub's documented semantics.

These examples come from GitHub's own CODEOWNERS documentation. The headline
research number depends on this matcher, so over-matching would silently shrink
the 'uncovered' count. Do not relax these.
"""

import pytest

from ovrin.codeowners import Owners, parse


def matches(pattern: str, path: str) -> bool:
    return bool(Owners(parse(pattern + "  @x\n"), "CODEOWNERS").owners_for(path))


# (pattern, path, should_match) — from GitHub's documented behaviour
CASES = [
    # star matches anything, at any depth
    ("*", "README.md", True),
    ("*", "deep/nested/file.md", True),
    # extension glob at any depth
    ("*.js", "a.js", True),
    ("*.js", "src/deep/a.js", True),
    ("*.js", "a.md", False),
    # THE BUG: docs/* matches one level, not deeper
    ("docs/*", "docs/getting-started.md", True),
    ("docs/*", "docs/build/troubleshooting.md", False),
    # anchored directory matches the dir and everything under it
    ("/build/logs/", "build/logs/output.txt", True),
    ("/build/logs/", "build/logs/deep/output.txt", True),
    ("/build/logs/", "src/build/logs/output.txt", False),
    # unanchored directory matches at any depth
    ("apps/", "apps/x/y.md", True),
    ("apps/", "sub/apps/x/y.md", True),
    # anchored directory only at root
    ("/apps/", "apps/a.md", True),
    ("/apps/", "sub/apps/a.md", False),
    # ** crosses directories
    ("**/logs", "logs", True),
    ("**/logs", "a/b/logs", True),
    # bare filename matches at any depth (this is why nested AGENTS.md is covered)
    ("AGENTS.md", "AGENTS.md", True),
    ("AGENTS.md", "packages/api/AGENTS.md", True),
    # anchored filename only at root
    ("/AGENTS.md", "AGENTS.md", True),
    ("/AGENTS.md", "packages/api/AGENTS.md", False),
]


@pytest.mark.parametrize("pattern,path,expect", CASES)
def test_github_semantics(pattern, path, expect):
    assert matches(pattern, path) is expect


def test_last_match_wins():
    o = Owners(parse("*  @all\nAGENTS.md  @platform\n"), "CODEOWNERS")
    assert o.owners_for("AGENTS.md") == ("@platform",)


def test_match_returns_rule_evidence():
    o = Owners(parse("*  @all\nAGENTS.md  @platform\n"), "CODEOWNERS")
    r = o.match("AGENTS.md")
    assert r.pattern == "AGENTS.md" and r.line == 2


def test_missing_file(tmp_path):
    assert not Owners.load(tmp_path).present


def test_pattern_with_no_owners_removes_ownership():
    # A pattern with no owners clears ownership (GitHub behaviour).
    o = Owners(parse("*  @all\nAGENTS.md\n"), "CODEOWNERS")
    assert o.owners_for("AGENTS.md") == ()


def test_gitlab_path_not_in_locations():
    from ovrin.codeowners import LOCATIONS
    assert ".gitlab/CODEOWNERS" not in LOCATIONS
    assert LOCATIONS == (".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
