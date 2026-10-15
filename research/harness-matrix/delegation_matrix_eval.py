#!/usr/bin/env python3
"""Delegation-policy 2x2 matrix evaluation.

The paper's central claim is that neither provenance (origin class) nor
repository governance (CODEOWNERS coverage) is the delegation decision.
Only D(s, c) is. This script runs the 2x2 that isolates that claim.

    Origin       Governance   Delegation D(s,c)   Correct action
    -----------  -----------  ------------------  --------------
    first-party  covered      1                   ALLOW
    third-party  covered      0                   BLOCK
    third-party  uncovered    1                   ALLOW
    third-party  uncovered    0                   BLOCK

Every cell is constructed as a synthetic Ovrin manifest with the specified
(origin, enforceable, delegated) triple. We run `enforce_all` under a
policy that expresses the correct D, then check that the emitted action
matches the "correct action" column. The N repetitions per cell are
present to catch nondeterministic policy evaluation; because the gate is
deterministic, we expect 100% agreement per cell.

Also runs a *heuristic-baseline* comparison: what does the pre-delegation
static gate do on the same 2x2? This shows the delegation gate is not
merely re-encoding the same heuristic.

Output: research/harness-matrix/delegation_matrix_report.md and
        research/harness-matrix/delegation_matrix_raw.jsonl
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ovrin.enforce import enforce_all
from ovrin.delegation import load_policy_from_string


REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_MD = Path(__file__).resolve().parent / "delegation_matrix_report.md"
OUT_JSONL = Path(__file__).resolve().parent / "delegation_matrix_raw.jsonl"


POLICY_YAML = """
version: 1
default:
  instruction: false
delegations:
  # Cell 1: first-party is delegated over src/
  - source: "repo:default"
    context:
      paths: ["src/**"]
    authority:
      instruction: true

  # Cell 3: policy-pack is delegated over its own subtree
  - source: "pkg:npm/policy-pack@1.0.0"
    context:
      paths: ["vendor/policy-pack/**"]
    authority:
      instruction: true

  # Cell 2 and Cell 4: no positive rule; default (deny) fires.
"""


@dataclass
class Cell:
    name: str
    origin_class: str
    enforceable: bool | None  # governance coverage
    delegated: bool
    package: dict | None
    path: str
    context_path: str
    expected_action: str

    def manifest_entry(self, harness: str = "claude-code") -> dict:
        e = {
            "path": self.path,
            "origin": {"class": self.origin_class},
            "review": {"ruleMatches": self.enforceable is True,
                       "enforceable": self.enforceable},
            "reachability": {
                harness: {"verdict": "loaded", "confidence": "documented"},
            },
        }
        if self.package:
            e["origin"]["package"] = self.package
        return e


CELLS = [
    Cell(
        name="Cell 1 (first-party, covered, delegated)",
        origin_class="repo", enforceable=True, delegated=True,
        package=None,
        path="CLAUDE.md", context_path="src/main.py",
        expected_action="ALLOW",
    ),
    Cell(
        name="Cell 2 (third-party, covered, NOT delegated)",
        origin_class="installed-dependency", enforceable=True, delegated=False,
        package={"ecosystem": "npm", "name": "rogue", "version": "1.0.0"},
        path="node_modules/rogue/CLAUDE.md", context_path="src/main.py",
        expected_action="BLOCK",
    ),
    Cell(
        name="Cell 3 (third-party, uncovered, delegated)",
        origin_class="installed-dependency", enforceable=None, delegated=True,
        package={"ecosystem": "npm", "name": "policy-pack", "version": "1.0.0"},
        path="vendor/policy-pack/CLAUDE.md",
        context_path="vendor/policy-pack/lib.py",
        expected_action="ALLOW",
    ),
    Cell(
        name="Cell 4 (third-party, uncovered, NOT delegated)",
        origin_class="installed-dependency", enforceable=None, delegated=False,
        package={"ecosystem": "npm", "name": "unknown", "version": "1.0.0"},
        path="node_modules/unknown/CLAUDE.md", context_path="src/main.py",
        expected_action="BLOCK",
    ),
]


def run(n_per_cell: int = 50) -> dict:
    policy = load_policy_from_string(POLICY_YAML)
    results = []
    baseline_results = []
    for cell in CELLS:
        manifest = {"instructions": [cell.manifest_entry()]}
        # With delegation policy
        agree = 0
        for i in range(n_per_cell):
            r = enforce_all(manifest, "claude-code", REPO_ROOT,
                            policy=policy, context_path=cell.context_path)
            if r.decisions[0].action == cell.expected_action:
                agree += 1
        # Without policy (heuristic baseline: what does the static gate say?)
        b_agree = 0
        for i in range(n_per_cell):
            r = enforce_all(manifest, "claude-code", REPO_ROOT)
            if r.decisions[0].action == cell.expected_action:
                b_agree += 1
        results.append({
            "cell": cell.name,
            "origin": cell.origin_class,
            "enforceable": cell.enforceable,
            "delegated": cell.delegated,
            "expected_action": cell.expected_action,
            "N": n_per_cell,
            "delegation_gate_agree": agree,
            "delegation_gate_disagree": n_per_cell - agree,
        })
        baseline_results.append({
            "cell": cell.name,
            "expected_action": cell.expected_action,
            "N": n_per_cell,
            "static_gate_agree": b_agree,
            "static_gate_disagree": n_per_cell - b_agree,
        })

    return {
        "policy_yaml": POLICY_YAML,
        "results_delegation_gate": results,
        "results_static_baseline": baseline_results,
    }


def render_report(payload: dict) -> str:
    lines = []
    lines.append("# Delegation-Policy Matrix: 2x2 Evaluation")
    lines.append("")
    lines.append("Isolates the paper's central claim that neither origin class")
    lines.append("nor CODEOWNERS coverage is the delegation decision.")
    lines.append("")
    lines.append("## Policy under test")
    lines.append("")
    lines.append("```yaml")
    lines.append(payload["policy_yaml"].strip())
    lines.append("```")
    lines.append("")
    lines.append("## Cells")
    lines.append("")
    lines.append("| Cell | Origin | Governance | D(s,c) | Expected | N | Delegation gate agree | Static-baseline agree |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r, b in zip(payload["results_delegation_gate"],
                    payload["results_static_baseline"]):
        gov = ("covered" if r["enforceable"] is True
               else "uncovered" if r["enforceable"] is None
               else "not-enforceable")
        deleg = 1 if r["delegated"] else 0
        lines.append(
            f"| {r['cell']} | {r['origin']} | {gov} | {deleg} | {r['expected_action']} | "
            f"{r['N']} | {r['delegation_gate_agree']}/{r['N']} | "
            f"{b['static_gate_agree']}/{b['N']} |"
        )
    lines.append("")
    # Aggregate
    N = payload["results_delegation_gate"][0]["N"]
    d_total = sum(r["delegation_gate_agree"] for r in payload["results_delegation_gate"])
    s_total = sum(r["static_gate_agree"] for r in payload["results_static_baseline"])
    total_N = N * len(CELLS)
    lines.append("## Aggregate")
    lines.append("")
    lines.append(f"- Delegation gate: **{d_total}/{total_N} correct** across the 2x2.")
    lines.append(f"- Static heuristic baseline: **{s_total}/{total_N} correct** across the 2x2.")
    lines.append("")
    lines.append("## Reading")
    lines.append("")
    lines.append("Cell 2 (third-party, CODEOWNERS-covered, not delegated) is the")
    lines.append("**paper's central discriminator**. A gate that treats governance as")
    lines.append("delegation will ALLOW here. The delegation gate BLOCKs it, exactly")
    lines.append("because D(s,c)=0 despite governance coverage. This isolates the")
    lines.append("claim `reviewed != authorized`.")
    lines.append("")
    lines.append("Cell 3 (third-party, uncovered, delegated) is the counterpart. A")
    lines.append("gate that treats third-party origin as unauthorized will BLOCK")
    lines.append("here. The delegation gate ALLOWs it because D(s,c)=1. This")
    lines.append("isolates the claim `third-party != unauthorized`.")
    return "\n".join(lines) + "\n"


def main() -> int:
    payload = run(n_per_cell=50)
    OUT_MD.write_text(render_report(payload), encoding="utf-8")
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in payload["results_delegation_gate"]:
            f.write(json.dumps({"gate": "delegation", **r}) + "\n")
        for r in payload["results_static_baseline"]:
            f.write(json.dumps({"gate": "static-baseline", **r}) + "\n")
    print(f"wrote {OUT_MD}")
    print(f"wrote {OUT_JSONL}")
    # Print a compact summary
    for r in payload["results_delegation_gate"]:
        print(f"  {r['cell']}: {r['delegation_gate_agree']}/{r['N']} "
              f"expected {r['expected_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
