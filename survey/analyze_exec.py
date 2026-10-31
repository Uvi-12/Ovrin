#!/usr/bin/env python3
"""Turn exec-crawl records into ecosystem prevalence numbers for the EXECUTING
agent-config supply chain — the executing analog of analyze.py.

Reports per (stratum, language) and refuses to pool silently. Truncated/error
trees are excluded from denominators, never counted as a clean negative.
"Auto-executing" means config that loads/runs at trust time (MCP servers, hooks);
skills are model-invoked, so they are reported separately and never inflate the
auto-executing headline. Every proportion carries a count, a denominator, and a
95% Wilson interval; config-level rates are also bootstrapped by repository.

Definitions (stated so a reviewer can check them):
  auto-exec config   kind in {mcp, hooks}  (skills excluded from the headline)
  third-party        origin in {vendored, installed-dependency}
  review-enforced    first-party AND covered by an enforceable CODEOWNERS rule
  ungoverned exec    an auto-exec config that is NOT review-enforced
                     (third-party, or uncovered/absent CODEOWNERS)

    python sweep/analyze_exec.py out/exec-*.jsonl --json-out out/analysis-exec.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

AUTO_KINDS = {"mcp", "hooks"}
THIRD_PARTY = {"vendored", "installed-dependency"}


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
        return (f"  {label:<48} n/a (0/0)", {"k": k, "n": n})
    txt = (f"  {label:<48} {k}/{n}  ({p*100:.1f}%, 95% CI {lo*100:.1f}-{hi*100:.1f})")
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


# --- per-record accessors --------------------------------------------------

def auto_configs(rec: dict) -> list[dict]:
    return [c for c in rec.get("execConfigs", []) if c.get("kind") in AUTO_KINDS]


def skills(rec: dict) -> list[dict]:
    return [c for c in rec.get("execConfigs", []) if c.get("kind") == "skill"]


def is_third_party(c: dict) -> bool:
    return c.get("origin") in THIRD_PARTY


def review_enforced(c: dict) -> bool:
    # enforceable review == first-party AND a CODEOWNERS rule with owners covers it
    return c.get("origin") == "first-party" and c.get("coverageStatus") == "covered"


def is_ungoverned(c: dict) -> bool:
    return not review_enforced(c)


def report_group(name: str, recs: list[dict], out: dict) -> list[str]:
    lines = [f"\n=== {name} ==="]
    g: dict = out.setdefault(name, {})

    usable = [r for r in recs if r.get("crawlStatus") == "ok"]
    truncated = sum(1 for r in recs if r.get("crawlStatus") == "truncated")
    errored = sum(1 for r in recs if r.get("crawlStatus") in ("error", "empty-or-error"))
    total = len(usable)
    lines.append(f"  usable repositories (excl. truncated/error): {total}")
    if truncated:
        lines.append(f"  excluded, truncated tree: {truncated}")
    if errored:
        lines.append(f"  excluded, error/empty: {errored}")
    g.update(usableRepos=total, truncatedExcluded=truncated, errorExcluded=errored)
    if not total:
        return lines

    # ---- RQ-E1 prevalence of auto-executing config ------------------------
    lines.append("\n RQ-E1 prevalence of auto-executing agent config (MCP servers + hooks)")
    with_auto = [r for r in usable if auto_configs(r)]
    ln, d = stat("repos with an auto-executing config", len(with_auto), total)
    lines.append(ln); g["prevalenceAutoExec"] = d

    with_tp = [r for r in usable if any(is_third_party(c) for c in auto_configs(r))]
    ln, d = stat("repos with THIRD-PARTY auto-exec config", len(with_tp), total)
    lines.append(ln); g["prevalenceThirdPartyExec"] = d

    # headline: ungoverned executing config present in the repo
    with_ung = [r for r in usable if any(is_ungoverned(c) for c in auto_configs(r))]
    ln, d = stat("repos with UNGOVERNED auto-exec config  <-- headline", len(with_ung), total)
    lines.append(ln); g["prevalenceUngovernedExec"] = d

    # by kind
    by_kind = Counter(c["kind"] for r in with_auto for c in auto_configs(r))
    for k, v in by_kind.most_common():
        lines.append(f"    kind {k:<10} {v} config file(s)")
    g["autoConfigsByKind"] = dict(by_kind)

    # ---- RQ-E2 provenance of the executing config -------------------------
    all_auto = [c for r in usable for c in auto_configs(r)]
    lines.append("\n RQ-E2 provenance of auto-executing config files")
    g["autoConfigTotal"] = len(all_auto)
    by_origin = Counter(c.get("origin", "?") for c in all_auto)
    for o in ("first-party", "vendored", "installed-dependency"):
        ln, d = stat(f"origin {o}", by_origin.get(o, 0), len(all_auto))
        lines.append(ln); g.setdefault("origin", {})[o] = d

    # ---- RQ-E3 review coverage (the governance gap) -----------------------
    lines.append("\n RQ-E3 review coverage of auto-executing config")
    scorable = [c for c in all_auto if c.get("coverageStatus") in ("covered", "uncovered")]
    uncovered = [c for c in scorable if c["coverageStatus"] == "uncovered"]
    ln, d = stat("auto-exec configs OUTSIDE CODEOWNERS coverage", len(uncovered), len(scorable))
    lines.append(ln); g["fileCoverageGap"] = d
    no_co = sum(1 for c in all_auto if c.get("coverageStatus") == "no-codeowners")
    if no_co:
        lines.append(f"      (+{no_co} configs in repos with no CODEOWNERS at all — also ungoverned)")
        g["configsNoCodeowners"] = no_co

    ungoverned = [c for c in all_auto if is_ungoverned(c)]
    ln, d = stat("auto-exec configs that are UNGOVERNED (config-level)", len(ungoverned), len(all_auto))
    lines.append(ln); g["ungovernedConfigRate"] = d

    # bootstrap the config-level ungoverned rate by repository
    per_repo = [[is_ungoverned(c) for c in auto_configs(r)] for r in with_auto]
    lo, hi = bootstrap(per_repo)
    if not math.isnan(lo):
        lines.append(f"      bootstrap-by-repo 95% CI: {lo*100:.1f}-{hi*100:.1f}")
        g["ungovernedConfigRate"]["bootstrapCI95"] = [round(lo * 100, 2), round(hi * 100, 2)]

    # by depth
    root = [c for c in scorable if "/" not in c["path"]]
    deep = [c for c in scorable if "/" in c["path"]]
    lines.append("\n RQ-E3b coverage by depth")
    ln, d = stat("root-level configs uncovered",
                 sum(c["coverageStatus"] == "uncovered" for c in root), len(root))
    lines.append(ln); g["rootUncovered"] = d
    ln, d = stat("nested configs uncovered",
                 sum(c["coverageStatus"] == "uncovered" for c in deep), len(deep))
    lines.append(ln); g["nestedUncovered"] = d

    # ---- RQ-E4 capability bill of materials -------------------------------
    lines.append("\n RQ-E4 declared capabilities across auto-exec config (the BOM)")
    caps = Counter(cap for c in all_auto for cap in (c.get("capabilities") or []))
    for cap, v in caps.most_common():
        p, lo, hi = wilson(v, len(all_auto))
        lines.append(f"    {cap:<18} {v}/{len(all_auto)}  ({p*100:.1f}%, CI {lo*100:.1f}-{hi*100:.1f})")
    g["capabilityBOM"] = {cap: v for cap, v in caps.items()}
    # process execution carried by third-party config is the sharpest cut
    tp_proc = sum(1 for c in all_auto if is_third_party(c) and "process_exec" in (c.get("capabilities") or []))
    ln, d = stat("configs: third-party AND declare process execution", tp_proc, len(all_auto))
    lines.append(ln); g["thirdPartyProcessExec"] = d

    # ---- skills reported separately (model-invoked, not auto-exec) --------
    all_skills = [c for r in usable for c in skills(r)]
    if all_skills:
        lines.append("\n (reported separately — model-invoked, NOT in the auto-exec headline)")
        with_skill = [r for r in usable if skills(r)]
        ln, d = stat("repos carrying a skill", len(with_skill), total)
        lines.append(ln); g["prevalenceSkill"] = d
        bundled = sum(1 for c in all_skills if c.get("bundledScript"))
        ln, d = stat("skills shipping a bundled script", bundled, len(all_skills))
        lines.append(ln); g["skillsWithBundledScript"] = d
    return lines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json-out")
    a = ap.parse_args()
    recs = load(a.paths)
    if not recs:
        print("no records", file=sys.stderr)
        return 1

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
    print("\nPer (stratum, language). Do NOT pool across strata/languages without")
    print("calling it an equal-weight stratified estimate. 'active'/'top' strata")
    print("characterise prevalence; 'hasmcp'/'hasfile' characterise governance")
    print("among repos that already carry the file (denominator is conditional).")

    if a.json_out:
        Path(a.json_out).write_text(json.dumps(out, indent=2), encoding="utf-8")
        print(f"\nwrote {a.json_out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
