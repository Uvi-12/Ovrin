"""Format scope semantics. Path position is the independent variable in the
research, so a root-anchored format must not match the same filename inside a
dependency, and a bare filename must match at any depth."""

from ovrin.formats import load, match_format


def fam(path):
    f = match_format(path, load())
    return f.family if f else None


def test_any_depth_filename_matches_nested():
    assert fam("AGENTS.md") == "agents"
    assert fam("packages/api/AGENTS.md") == "agents"
    assert fam("node_modules/x/AGENTS.md") == "agents"


def test_repo_root_only_does_not_match_nested():
    assert fam(".github/copilot-instructions.md") == "copilot"
    assert fam("sub/.github/copilot-instructions.md") is None


def test_anchored_subtree_allows_its_own_subdirs():
    assert fam(".github/instructions/a.instructions.md") == "copilot"
    assert fam(".github/instructions/backend/a.instructions.md") == "copilot"


def test_anchored_subtree_not_matched_as_suffix_in_dependency():
    assert fam("pkg/.github/instructions/a.instructions.md") is None


def test_cursor_rules_glob_scoped():
    assert fam(".cursor/rules/style.mdc") == "cursor"
    # not a suffix inside a vendored tree
    assert fam("vendor/dep/.cursor/rules/style.mdc") is None
