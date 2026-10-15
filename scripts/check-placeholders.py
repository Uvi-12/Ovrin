#!/usr/bin/env python3
"""Fail if release-blocking placeholder strings remain. Run before tagging a release."""
import pathlib
import sys

# Tokens that must never appear in a public release.
BAD = ["OWNER", "example.com", "replace this notice",
       "anonymous.4open", "Anonymous", "Marginalia"]

# TODO/FIXME are intentional canary content inside the study fixtures, so they
# are only treated as placeholders outside those trees.
TODO_TOKENS = ["TODO", "FIXME"]
FIXTURE_PARTS = {"research", "harness_cases"}

root = pathlib.Path(__file__).resolve().parent.parent
hits = []
for p in root.rglob("*"):
    if not p.is_file() or p.suffix not in {".py", ".md", ".toml", ".yaml", ".yml", ".cff"}:
        continue
    if any(x in p.parts for x in (".git", "dist", "build", ".venv")):
        continue
    rel = p.relative_to(root)
    if rel.name == "check-placeholders.py":        # don't flag our own token list
        continue
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        continue
    in_fixture = any(part in FIXTURE_PARTS for part in rel.parts)
    tokens = BAD if in_fixture else BAD + TODO_TOKENS
    for token in tokens:
        if token in text:
            hits.append(f"{rel}: {token}")

if hits:
    print("placeholders remaining (must be resolved before release):")
    for h in hits:
        print("  " + h)
    sys.exit(1)
print("no placeholders")
