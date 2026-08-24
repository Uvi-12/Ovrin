"""The survey must use the same discovery and CODEOWNERS logic as the scanner.
These tests pin that shared behaviour."""

from ovrin.survey_probe import coverage_for, instruction_paths_in


def test_recursive_discovery_finds_nested():
    paths = ["AGENTS.md", "packages/api/AGENTS.md", ".cursor/rules/a.mdc",
             ".github/instructions/x.instructions.md", "src/main.py", "README.md"]
    found = {f["path"] for f in instruction_paths_in(paths)}
    assert "packages/api/AGENTS.md" in found       # nested, missed by old survey
    assert ".cursor/rules/a.mdc" in found          # glob pattern
    assert ".github/instructions/x.instructions.md" in found
    assert "README.md" not in found
    assert "src/main.py" not in found


def test_coverage_no_codeowners():
    c = coverage_for(None, None, "AGENTS.md")
    assert c["codeownersPresent"] is False
    assert c["coverageStatus"] == "no-codeowners"


def test_coverage_covered():
    c = coverage_for("AGENTS.md  @team\n", ".github/CODEOWNERS", "AGENTS.md")
    assert c["ruleMatches"] is True
    assert c["coverageStatus"] == "covered"
    assert c["matchedOwners"] == ["@team"]


def test_coverage_uncovered_when_no_rule_matches():
    # A CODEOWNERS that covers docs but not the instruction file.
    c = coverage_for("/docs/  @docs-team\n", ".github/CODEOWNERS", "AGENTS.md")
    assert c["ruleMatches"] is False
    assert c["coverageStatus"] == "uncovered"


def test_coverage_last_match_wins():
    co = "*  @all\nAGENTS.md  @platform\n"
    c = coverage_for(co, ".github/CODEOWNERS", "AGENTS.md")
    assert c["matchedOwners"] == ["@platform"]
    assert c["matchedRuleLine"] == 2
