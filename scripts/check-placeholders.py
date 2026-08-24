#!/usr/bin/env python3
"""Fail if placeholder strings remain. Run before tagging a release."""
import pathlib
import sys

BAD = ["OWNER", "TODO", "FIXME", "example.com", "replace this notice"]
root = pathlib.Path(__file__).resolve().parent.parent
hits = []
for p in root.rglob("*"):
    if p.is_file() and p.suffix in {".py", ".md", ".toml", ".yaml", ".yml", ".cff"}:
        if any(x in p.parts for x in (".git", "dist", "build")):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for token in BAD:
            if token in text:
                hits.append(f"{p.relative_to(root)}: {token}")
if hits:
    print("placeholders remaining (expected before first release):")
    for h in hits:
        print("  " + h)
    sys.exit(1)
print("no placeholders")
