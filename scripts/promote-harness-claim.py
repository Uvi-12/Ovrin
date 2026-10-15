#!/usr/bin/env python3
"""Promote a single harness behavioural claim to confidence: observed.

Use this ONLY after actually running the agent and watching it load (or not
load) the instruction file — e.g. via research/harness-matrix/observe.py. A
claim marked `observed` asserts a real run happened; do not flip it otherwise.

    python scripts/promote-harness-claim.py \\
        --harness codex-cli --claim root_loading \\
        --evidence tests/harness_cases/codex-cli/root-agents-md/RESULT.md

Edits src/ovrin/data/harnesses.yaml in place. Review the diff before committing.
"""
import argparse
import pathlib
import sys

import yaml

DATA = pathlib.Path(__file__).resolve().parent.parent / "src" / "ovrin" / "data" / "harnesses.yaml"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--harness", required=True)
    ap.add_argument("--claim", required=True)
    ap.add_argument("--evidence", required=True,
                    help="path to the recorded observation (e.g. a RESULT.md)")
    a = ap.parse_args()

    doc = yaml.safe_load(DATA.read_text(encoding="utf-8"))
    for h in doc.get("harnesses", []):
        if h.get("id") == a.harness:
            claims = h.setdefault("claims", {})
            if a.claim not in claims:
                print(f"error: harness '{a.harness}' has no claim '{a.claim}'", file=sys.stderr)
                return 2
            claims[a.claim]["confidence"] = "observed"
            claims[a.claim]["evidence"] = a.evidence
            DATA.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True),
                            encoding="utf-8")
            print(f"promoted {a.harness}/{a.claim} -> observed (evidence: {a.evidence})")
            print("review the diff: git diff src/ovrin/data/harnesses.yaml")
            return 0
    print(f"error: no harness '{a.harness}'", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
