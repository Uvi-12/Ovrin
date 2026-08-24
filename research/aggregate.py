#!/usr/bin/env python3
"""Aggregate many the carriage study and the resolution experiments result files into the two headline rates.

the carriage study (Z%): reads every research/reachability/results/*.json produced by
resolve.py and reports how many resolved dependency trees carried an instruction
file the project did not author, and of those carriers, how many were reachable
by at least one harness versus unverified.

the resolution experiments (D%): reads a directory of observe.py *.json summaries and reports pairwise
harness disagreement on the same case: how often two harnesses reach different
verdicts for the same instruction path.

    python research/aggregate.py \
        --rq3 research/reachability/results \
        --rq4 research/harness-matrix/results \
        --out research/AGGREGATE.json

Either --rq3 or --rq4 may be omitted. Every proportion carries a Wilson 95% CI.
"""

from __future__ import annotations

import argparse
import json
import math
from itertools import combinations
from pathlib import Path


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan"), float("nan")]
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    return [round(p * 100, 2), round(max(0.0, centre - half) * 100, 2),
            round(min(1.0, centre + half) * 100, 2)]


def load_json_dir(path: Path) -> list[dict]:
    out = []
    for f in sorted(path.glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def aggregate_rq3(results: list[dict]) -> dict:
    """Z%: carriage and reachability across resolved trees."""
    ok = [r for r in results if r.get("status") == "ok"]
    trees = len(ok)
    trees_with_carrier = sum(1 for r in ok if r.get("externallyCarried", 0) > 0)
    all_carriers = [c for r in ok for c in r.get("carried", [])]
    total_carriers = len(all_carriers)
    reachable = sum(1 for r in ok for _ in range(r.get("carriersReachableBySomeHarness", 0)))
    unverified = sum(1 for r in ok for _ in range(r.get("carriersUnverifiedOnly", 0)))
    return {
        "resolvedTrees": trees,
        "treesCarryingInstructions": {
            "count": trees_with_carrier, "of": trees,
            "ci95": wilson(trees_with_carrier, trees),
        },
        "totalExternalCarriers": total_carriers,
        "carriersReachableBySomeHarness": {
            "count": reachable, "of": total_carriers,
            "ci95": wilson(reachable, total_carriers),
        },
        "carriersUnverifiedOnly": {
            "count": unverified, "of": total_carriers,
            "ci95": wilson(unverified, total_carriers),
        },
        "byEcosystem": _rq3_by_ecosystem(ok),
    }


def _rq3_by_ecosystem(ok: list[dict]) -> dict:
    eco: dict[str, dict] = {}
    for r in ok:
        e = r.get("ecosystem", "?")
        d = eco.setdefault(e, {"trees": 0, "carriers": 0})
        d["trees"] += 1
        d["carriers"] += r.get("externallyCarried", 0)
    return eco


def aggregate_rq4(results: list[dict]) -> dict:
    """D%: pairwise harness disagreement on the same case/path.

    Each the resolution experiments result records, per case, a mapping of harness -> verdict for the
    instruction path under test. Two harnesses 'disagree' when their verdicts
    differ (e.g. one loads, one does not-discover). We report disagreeing pairs
    over all comparable pairs, across all cases.
    """
    total_pairs = 0
    disagreeing = 0
    per_case = []
    observed_claims = set()
    for r in results:
        verdicts = r.get("harnessVerdicts", {})
        harnesses = sorted(verdicts)
        case_pairs = case_disagree = 0
        for a, b in combinations(harnesses, 2):
            total_pairs += 1
            case_pairs += 1
            if verdicts[a] != verdicts[b]:
                disagreeing += 1
                case_disagree += 1
        if r.get("claim") and r.get("loadingVerdict") == "loaded":
            observed_claims.add((r.get("agent"), r.get("claim")))
        per_case.append({
            "case": r.get("case", "?"),
            "harnesses": len(harnesses),
            "disagreeingPairs": case_disagree,
            "totalPairs": case_pairs,
        })
    return {
        "casesAnalyzed": len(results),
        "observedClaims": sorted(f"{a}:{c}" for a, c in observed_claims),
        "pairwiseDisagreement": {
            "count": disagreeing, "of": total_pairs,
            "ci95": wilson(disagreeing, total_pairs),
        },
        "perCase": per_case,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rq3", help="directory of resolve.py *.json results")
    ap.add_argument("--rq4", help="directory of observe.py *.json summaries")
    ap.add_argument("--out", help="write aggregate JSON here")
    a = ap.parse_args()

    out: dict = {}
    lines = []
    if a.rq3:
        rq3 = aggregate_rq3(load_json_dir(Path(a.rq3)))
        out["rq3"] = rq3
        z = rq3["treesCarryingInstructions"]
        lines.append("the carriage study dependency-tree carriage (Z%)")
        lines.append(f"  resolved trees: {rq3['resolvedTrees']}")
        lines.append(f"  trees carrying a third-party instruction: "
                     f"{z['count']}/{z['of']} ({z['ci95'][0]}%, 95% CI {z['ci95'][1]}-{z['ci95'][2]})")
        rc = rq3["carriersReachableBySomeHarness"]
        lines.append(f"  carriers reachable by >=1 harness: "
                     f"{rc['count']}/{rc['of']} ({rc['ci95'][0]}%, 95% CI {rc['ci95'][1]}-{rc['ci95'][2]})")
        lines.append(f"  by ecosystem: {rq3['byEcosystem']}")
    if a.rq4:
        rq4 = aggregate_rq4(load_json_dir(Path(a.rq4)))
        out["rq4"] = rq4
        d = rq4["pairwiseDisagreement"]
        lines.append("")
        lines.append("the resolution experiments cross-harness disagreement (D%)")
        lines.append(f"  cases analyzed: {rq4['casesAnalyzed']}")
        lines.append(f"  observed claims: {', '.join(rq4['observedClaims']) or 'none'}")
        lines.append(f"  pairwise disagreement: "
                     f"{d['count']}/{d['of']} ({d['ci95'][0]}%, 95% CI {d['ci95'][1]}-{d['ci95'][2]})")

    print("\n".join(lines) if lines else "nothing to aggregate (pass --rq3 and/or --rq4)")
    if a.out:
        Path(a.out).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())