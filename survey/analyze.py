#!/usr/bin/env python3
"""Turn crawl records into the numbers for the talk.

Reports per (stratum, language) and refuses to pool silently. Truncated trees
are excluded from denominators. Primary prevalence counts only auto-loaded
instruction files; manually loaded ones (aider CONVENTIONS.md) are reported
separately so they cannot inflate the headline. Every proportion carries a
count, a denominator, and a 95% Wilson interval; file-level rates are
bootstrapped by repository.

    python survey/analyze.py survey/out/records-*.jsonl --json-out survey/out/analysis.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

AUTO_ACTIVATIONS = {"native-auto", "configurable", "legacy"}  # NOT "manual"


def load(paths: list[str]) -> list[dict]:
    out = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return (float("nan"), float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    return (p, max(0.0, centre - half), min(1.0, centre + half))


def stat(label: str, k: int, n: int) -> tuple[str, dict]:
    p, lo, hi = wilson(k, n)
    if math.isnan(p):
        return (f"  {label:<44} n/a", {"k": k, "n": n})
    txt = (f"  {label:<44} {k}/{n}  "
           f"({p*100:.1f}%, 95% CI {lo*100:.1f}-{hi*100:.1f})")
    return (txt, {"k": k, "n": n, "pct": round(p * 100, 2),
                  "ci95": [round(lo * 100, 2), round(hi * 100, 2)]})


def bootstrap(repos: list[list[bool]], iters: int = 2000, seed: int = 1) -> list[float]:
    rng = random.Random(seed)
    ne = [r for r in repos if r]
    if not ne:
        return [float("nan"), float("nan")]
    ests, m = [], len(ne)
    for _ in range(iters):
        flat = [b for _ in range(m) for b in ne[rng.randrange(m)]]
        if flat:
            ests.append(sum(flat) / len(flat))
    ests.sort()
    if not ests:
        return [float("nan"), float("nan")]
    return [ests[int(0.025 * len(ests))], ests[int(0.975 * len(ests))]]


def auto_files(rec: dict) -> list[dict]:
    return [f for f in rec.get("instructionFiles", [])
            if f.get("activation") in AUTO_ACTIVATIONS]


def manual_files(rec: dict) -> list[dict]:
    return [f for f in rec.get("instructionFiles", [])
            if f.get("activation") == "manual"]


def report_group(name: str, recs: list[dict], out: dict) -> list[str]:
    lines = [f"\n=== {name} ==="]
    g: dict = out.setdefault(name, {})

    # denominators exclude truncated/error trees
    usable = [r for r in recs if r.get("crawlStatus") == "ok"]
    truncated = sum(1 for r in recs if r.get("crawlStatus") == "truncated")
    total = len(usable)
    lines.append(f"  usable repositories (excl. truncated/error): {total}")
    if truncated:
        lines.append(f"  excluded, truncated tree: {truncated}")
    g["usableRepos"] = total
    g["truncatedExcluded"] = truncated
    if not total:
        return lines

    # RQ1 prevalence, AUTO formats only
    withauto = [r for r in usable if auto_files(r)]
    lines.append("\n RQ1 prevalence (auto-loaded formats only)")
    ln, d = stat("repositories with an auto instruction file", len(withauto), total)
    lines.append(ln)
    g["prevalenceAuto"] = d
    # manual reported separately
    withmanual = [r for r in usable if manual_files(r) and not auto_files(r)]
    ln, d = stat("repos with ONLY a manual instruction file", len(withmanual), total)
    lines.append(ln)
    g["manualOnly"] = d

    fam = Counter(f["family"] for r in withauto for f in auto_files(r))
    for k, v in fam.most_common():
        lines.append(f"    family {k:<26} {v}")

    # RQ2 review coverage, the headline
    lines.append("\n RQ2 review coverage")
    have_co = [r for r in withauto if r.get("codeownersPath")]
    ln, d = stat("repos w/ instructions that have CODEOWNERS", len(have_co), len(withauto))
    lines.append(ln)
    g["codeownersAdoption"] = d

    all_in_co = [f for r in have_co for f in auto_files(r)]
    unreadable = [f for f in all_in_co if f.get("coverageStatus") == "unreadable-codeowners"]
    files_in_co = [f for f in all_in_co if f.get("coverageStatus") in ("covered", "uncovered")]
    uncovered = [f for f in files_in_co if f.get("coverageStatus") == "uncovered"]
    ln, d = stat("instruction files OUTSIDE CODEOWNERS coverage", len(uncovered), len(files_in_co))
    lines.append(ln)
    g["fileCoverageGap"] = d
    if unreadable:
        lines.append(f"      excluded, unreadable CODEOWNERS: {len(unreadable)}")
        g["unreadableCodeowners"] = len(unreadable)

    def _scorable(r):
        return [f for f in auto_files(r) if f.get("coverageStatus") in ("covered", "uncovered")]
    per_repo = [[f.get("coverageStatus") == "uncovered" for f in _scorable(r)] for r in have_co]
    lo, hi = bootstrap(per_repo)
    if not math.isnan(lo):
        lines.append(f"      bootstrap-by-repo 95% CI: {lo*100:.1f}-{hi*100:.1f}")
        g["fileCoverageGap"]["bootstrapCI95"] = [round(lo * 100, 2), round(hi * 100, 2)]

    repo_gap = sum(1 for r in have_co
                   if any(f.get("coverageStatus") == "uncovered" for f in auto_files(r)))
    ln, d = stat("repos with >=1 uncovered instruction", repo_gap, len(have_co))
    lines.append(ln)
    g["repoCoverageGap"] = d

    # coverage by depth
    root = [f for f in files_in_co if "/" not in f["path"]]
    deep = [f for f in files_in_co if "/" in f["path"]]
    lines.append("\n RQ2b coverage by depth")
    ln, d = stat("root-level files uncovered",
                 sum(f["coverageStatus"] == "uncovered" for f in root), len(root))
    lines.append(ln)
    g["rootUncovered"] = d
    ln, d = stat("nested files uncovered",
                 sum(f["coverageStatus"] == "uncovered" for f in deep), len(deep))
    lines.append(ln)
    g["nestedUncovered"] = d
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json-out", help="write a machine-readable snapshot")
    a = ap.parse_args()
    recs = load(a.paths)
    if not recs:
        print("no records", file=sys.stderr)
        return 1

    # group by stratum + language, never pool silently
    groups: dict[str, list[dict]] = {}
    for r in recs:
        key = f"{r.get('stratum', '?')}/{r.get('language') or 'any'}"
        groups.setdefault(key, []).append(r)

    out: dict = {"totalRecords": len(recs), "groups": {}}
    print(f"total records: {len(recs)} across {len(groups)} (stratum/language) groups")
    all_lines = []
    for name, rs in sorted(groups.items()):
        all_lines += report_group(name, rs, out["groups"])
    print("\n".join(all_lines))
    print("\nPer (stratum, language). Do not pool across languages without calling it")
    print("an equal-weight stratified estimate. See docs/methodology.md.")

    if a.json_out:
        Path(a.json_out).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nwrote {a.json_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
