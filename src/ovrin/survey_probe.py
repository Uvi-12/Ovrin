"""Shared logic the survey reuses, so the study and the scanner agree.

The survey must not carry its own smaller idea of what an instruction file is,
or its own weaker CODEOWNERS check. It imports the same format catalogue and the
same CODEOWNERS matcher the scanner uses, and applies them to a remote tree
fetched over the GitHub API.
"""

from __future__ import annotations

from .codeowners import Owners, parse
from .formats import load as load_formats
from .formats import match_format


def instruction_paths_in(tree_paths: list[str]) -> list[dict]:
    """Given every path in a repo tree, return the ones that are instruction
    files, tagged with family and activation from the shared catalogue."""
    formats = load_formats()
    out = []
    for path in tree_paths:
        fmt = match_format(path, formats)
        if fmt is not None:
            out.append({"path": path, "family": fmt.family, "activation": fmt.activation})
    return out


def coverage_for(codeowners_text: str | None, codeowners_path: str | None,
                 instruction_path: str, codeowners_present: bool | None = None) -> dict:
    """Test one instruction path against a repo's CODEOWNERS, using the same
    matcher the scanner uses. Returns the evidence the research protocol
    requires, including which rule matched.

    codeowners_present lets the caller distinguish a repo with no CODEOWNERS
    file (absent) from one where the file exists but could not be decoded
    (unreadable). An unreadable file must not be counted as covered OR
    uncovered; it is its own status."""
    if codeowners_present is None:
        codeowners_present = codeowners_text is not None
    if codeowners_text is None:
        status = "unreadable-codeowners" if codeowners_present else "no-codeowners"
        return {"codeownersPresent": bool(codeowners_present), "ruleMatches": False,
                "matchedOwners": [], "matchedPattern": None, "matchedRuleLine": None,
                "coverageStatus": status}
    owners = Owners(parse(codeowners_text), codeowners_path)
    rule = owners.match(instruction_path)
    return {
        "codeownersPresent": True,
        "ruleMatches": rule is not None and bool(rule.owners),
        "matchedOwners": list(rule.owners) if rule else [],
        "matchedPattern": rule.pattern if rule else None,
        "matchedRuleLine": rule.line if rule else None,
        "coverageStatus": "covered" if (rule and rule.owners) else "uncovered",
    }
