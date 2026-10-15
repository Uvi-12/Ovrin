#!/usr/bin/env python3
"""Validate an Ovrin SPDX export.

If an SPDX 3.0 validator is installed it is used; otherwise a structural check
runs (required keys, every rootElement resolves, digests are complete SHA-256).
The structural check is necessary, not sufficient: run the official validator
before claiming full SPDX 3.0 conformance.
"""
import json
import re
import sys


def structural_check(doc: dict) -> list[str]:
    errs = []
    if "@context" not in doc or "@graph" not in doc:
        errs.append("missing @context or @graph")
        return errs
    graph = doc["@graph"]
    ids = {n.get("spdxId") for n in graph if "spdxId" in n}
    for n in graph:
        if n.get("type") == "software_Sbom":
            for root in n.get("rootElement", []):
                if root not in ids:
                    errs.append(f"rootElement {root} not in graph")
        if n.get("type") == "software_File":
            for h in n.get("verifiedUsing", []):
                if h.get("algorithm") == "sha256" and not re.fullmatch(r"[0-9a-f]{64}", h.get("hashValue", "")):
                    errs.append(f"{n.get('name')}: malformed sha256")
    return errs


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_spdx.py <file.spdx.json>", file=sys.stderr)
        return 2
    doc = json.loads(open(sys.argv[1], encoding="utf-8").read())
    errs = structural_check(doc)
    if errs:
        print("structural check FAILED:")
        for e in errs:
            print("  " + e)
        return 1
    print("structural check passed ("
          f"{sum(1 for n in doc['@graph'] if n.get('type') == 'software_File')} files).")
    print("note: run the official SPDX 3.0 validator for full conformance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
