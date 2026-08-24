#!/usr/bin/env python3
"""the dependency-depth analysis — DEPENDENCY DEPTH ANALYSIS (no agent runs; pure analysis of the carriage study data).

Connects the carriage measurement to the precedence MECHANISM. Codex aggregates
instruction files root->leaf and files closer to the working dir override earlier
ones (they appear later in the concatenated prompt): precedence is POSITIONAL, and
depth determines position. Claude/Gemini discover nested files on subtree access.

So: how DEEP do real dependency-carried instruction files actually sit? If they sit
deep (several directories below root), then under positional precedence they occupy
the LATE (overriding) slots for any work in their subtree. This shows the carriage
result and the precedence result are the same phenomenon: ordinary dependency layout
places third-party instructions into positionally-dominant locations.

Reads research/rq3/results/rq3-*.jsonl, extracts every carriedInstructionFiles[].path,
computes directory depth (number of path separators), and reports the distribution
per ecosystem + pooled. Also flags vendor/node_modules containment. No network, no agent.

  python research/harness-matrix/dependency_depth.py \
      --results research/rq3/results --out research/rq3/results/depth-analysis.md
"""
from __future__ import annotations
import argparse, json, statistics as stats
from pathlib import Path
from collections import Counter

ECOS = ["cargo", "go", "npm", "python", "maven"]

# markers that indicate the file is inside a dependency tree (third-party region)
DEP_MARKERS = ("vendor/", "node_modules/", "_v/", "site-packages/", ".cargo/",
               "target/", "/.venv/", "venv/")


def depth_of(path: str) -> int:
    # directory depth = number of '/' separators (file at root => 0)
    return path.count("/")


def is_in_dep_tree(path: str) -> bool:
    p = path.lower()
    return any(m in p for m in DEP_MARKERS)


def analyze(results_dir: Path):
    per_eco = {}
    pooled_depths = []
    pooled_indep = 0
    pooled_total = 0
    for eco in ECOS:
        fp = results_dir / f"rq3-{eco}.jsonl"
        if not fp.exists():
            continue
        depths = []
        indep = 0
        total = 0
        example_deep = None
        with fp.open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                for cf in (r.get("carriedInstructionFiles") or []):
                    path = cf.get("path", "")
                    if not path:
                        continue
                    d = depth_of(path)
                    depths.append(d)
                    total += 1
                    if is_in_dep_tree(path):
                        indep += 1
                    if example_deep is None or d > depth_of(example_deep):
                        example_deep = path
        if total:
            per_eco[eco] = {
                "count": total,
                "inDepTree": indep,
                "inDepTreePct": round(100 * indep / total, 1),
                "depthMin": min(depths),
                "depthMedian": stats.median(depths),
                "depthMean": round(stats.mean(depths), 2),
                "depthMax": max(depths),
                "depthDist": dict(sorted(Counter(depths).items())),
                "deepestExample": example_deep,
            }
            pooled_depths += depths
            pooled_indep += indep
            pooled_total += total
    pooled = {}
    if pooled_total:
        pooled = {
            "count": pooled_total,
            "inDepTree": pooled_indep,
            "inDepTreePct": round(100 * pooled_indep / pooled_total, 1),
            "depthMin": min(pooled_depths),
            "depthMedian": stats.median(pooled_depths),
            "depthMean": round(stats.mean(pooled_depths), 2),
            "depthMax": max(pooled_depths),
            "depthDist": dict(sorted(Counter(pooled_depths).items())),
        }
    return per_eco, pooled


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="research/rq3/results")
    ap.add_argument("--out", default="research/rq3/results/depth-analysis.md")
    a = ap.parse_args()
    rd = Path(a.results)
    per_eco, pooled = analyze(rd)

    lines = ["# Seam 2 — dependency depth of carried instruction files",
             "",
             "Pure analysis of existing the carriage study carriage data (no agent runs). Depth = number",
             "of path separators in the carried file's path (root file = depth 0).",
             "Under positional precedence (Codex concatenates root->leaf; deeper = later =",
             "overriding), deeper files occupy the dominant slots for work in their subtree.",
             ""]
    if pooled:
        lines += [f"## Pooled (all ecosystems)",
                  f"- Carried instruction files analyzed: **{pooled['count']}**",
                  f"- Inside a dependency tree (vendor/node_modules/etc): "
                  f"**{pooled['inDepTree']} ({pooled['inDepTreePct']}%)**",
                  f"- Depth: min {pooled['depthMin']}, median **{pooled['depthMedian']}**, "
                  f"mean {pooled['depthMean']}, max {pooled['depthMax']}",
                  f"- Depth distribution: {pooled['depthDist']}",
                  ""]
    lines += ["## Per ecosystem", ""]
    lines += ["| Ecosystem | carried files | in dep-tree | in-tree % | median depth | mean | max |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for eco, v in per_eco.items():
        lines.append(f"| {eco} | {v['count']} | {v['inDepTree']} | {v['inDepTreePct']}% | "
                     f"{v['depthMedian']} | {v['depthMean']} | {v['depthMax']} |")
    lines += ["", "## Deepest example per ecosystem", ""]
    for eco, v in per_eco.items():
        lines.append(f"- **{eco}** (depth {depth_of(v['deepestExample'])}): "
                     f"`{v['deepestExample']}`")
    lines += ["", "## Honest reading",
              "- These are carried third-party instruction files from ordinary dependency",
              "  materialization. Their depth is a property of dependency layout, not intent.",
              "- Deeper placement => later position under root->leaf concatenation => higher",
              "  positional precedence for tasks within that subtree (Codex-documented).",
              "- This does NOT by itself prove cross-boundary control (that is the import-carriage mechanism); it",
              "  shows the raw material sits in positionally-dominant, dependency-tree",
              "  locations, connecting the carriage measurement to the precedence mechanism.",
              "- Depth is a structural fact; it is agent-independent. The precedence",
              "  CONSEQUENCE of depth is agent-specific (Codex positional; others differ).",
              ""]
    outp = Path(a.out)
    outp.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:40]))
    print(f"\nwrote {outp}")
    # also dump machine-readable
    (outp.parent / "depth-analysis.json").write_text(
        json.dumps({"perEcosystem": per_eco, "pooled": pooled}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
