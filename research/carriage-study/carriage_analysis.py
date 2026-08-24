#!/usr/bin/env python3
"""the carriage study-B/C/D: offline analysis over the the carriage study-A carriage JSONL files.

This runs entirely on the results already produced by drive.py — NO Docker, NO
network, NO cloning. It reads research/carriage-study/results/carriage-*.jsonl and computes:

  the carriage study-B  Provenance     Of the carried instruction files, which came from a
                        genuine THIRD-PARTY dependency (vs the project's own
                        vendored/first-party code). Answers "is this really
                        supply-chain carriage, not self-carriage?"

  the carriage study-C  Governance     Join carriage against the RQ2 CODEOWNERS signal: how
                        many carrier REPOS have no CODEOWNERS at all (ungoverned),
                        so a propagated instruction file lands where no reviewer
                        is assigned. Answers "does anyone govern these files?"

  the carriage study-D  Reachability   For each carried file, is it at a path a CWD-based agent
                        would actually discover? We classify by DEPTH and LOCATION
                        (repo-root-relative vs buried deep in a vendor tree),
                        producing a conservative DOCUMENTED_REACHABLE verdict.
                        We NEVER claim a file was LOADED — only that its location
                        is reachable by documented discovery rules.

Then it prints the the carriage study headline: W = third-party AND ungoverned AND reachable.

    python research/carriage-study/carriage_analysis.py \
        --results research/carriage-study/results \
        --records survey/out \
        --out research/carriage-study/results/carriage-results.json

Every proportion carries a Wilson 95% CI (same helper as aggregate.py).
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Wilson CI (identical to research/aggregate.py so numbers are consistent)
# ---------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [float("nan"), float("nan"), float("nan")]
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    return [round(p * 100, 2), round(max(0.0, centre - half) * 100, 2),
            round(min(1.0, centre + half) * 100, 2)]


# ---------------------------------------------------------------------------
# Per-ecosystem structure of a carried path.
#   vendor_prefix : the directory the resolver materialises deps into
#   pkg_from_path : extract a stable third-party package identity from the path,
#                   and the path RELATIVE TO THAT PACKAGE ROOT (for depth/D)
# A carried file is THIRD-PARTY when its path sits under the vendor prefix AND
# resolves to a package identity distinct from the host repo. Everything the
# resolver puts under these prefixes is, by construction, a resolved dependency
# (the host's own files are not copied there) — but we still record the package
# so the carriage study-B can report distinct third-party packages, not just files.
# ---------------------------------------------------------------------------


def _split_after(parts: list[str], anchor: str, take: int) -> tuple[str, str]:
    """Return (package_id, path_relative_to_package_root)."""
    i = parts.index(anchor)
    pkg_parts = parts[i + 1:i + 1 + take]
    pkg = "/".join(pkg_parts)
    rel = "/".join(parts[i + 1 + take:])
    return pkg, rel


def parse_carried(eco: str, path: str) -> tuple[str, str] | None:
    """Map a carried file path to (package_id, path_within_package).

    Returns None if the path does not sit under the ecosystem's vendor prefix
    (i.e. it is NOT third-party carriage — a safety check for the carriage study-B).
    """
    parts = path.split("/")
    try:
        if eco == "cargo":
            # _v/<crate>/...            e.g. _v/zerocopy/AGENTS.md
            if parts[0] != "_v":
                return None
            return _split_after(parts, "_v", 1)
        if eco == "go":
            # vendor/<host>/<org>/<repo>[/vN]/...
            # e.g. vendor/github.com/go-playground/validator/v10/CLAUDE.md
            if parts[0] != "vendor":
                return None
            # take 3 path components as the module id (host/org/repo); this is a
            # stable-enough identity for provenance counting.
            return _split_after(parts, "vendor", 3)
        if eco == "npm":
            # node_modules/<pkg>/...  OR node_modules/@scope/<pkg>/...
            if parts[0] != "node_modules":
                return None
            i = 0
            if parts[1].startswith("@"):
                pkg = "/".join(parts[1:3])
                rel = "/".join(parts[3:])
            else:
                pkg = parts[1]
                rel = "/".join(parts[2:])
            return pkg, rel
        if eco == "python":
            # _s/ansible_collections/<ns>/<name>/...  OR _s/<dist>/...
            if parts[0] != "_s":
                return None
            if len(parts) > 1 and parts[1] == "ansible_collections":
                pkg = "ansible:" + "/".join(parts[2:4])
                rel = "/".join(parts[4:])
                return pkg, rel
            return _split_after(parts, "_s", 1)
        if eco == "maven":
            # JARs seal files; nothing is exposed loose. If anything appears,
            # record it but it is an edge case.
            return ("/".join(parts[1:2]) if len(parts) > 1 else parts[0]), "/".join(parts[2:])
    except (ValueError, IndexError):
        return None
    return None


# ---------------------------------------------------------------------------
# the carriage study-D reachability classification (conservative, documentation-based).
#
# We do NOT load anything. We classify each carried file's LOCATION against the
# documented discovery behaviour of CWD-based agents, which look for instruction
# files at the working directory and walk UP toward the repo root — not deep
# into vendored dependency subtrees. So:
#
#   DOCUMENTED_REACHABLE : the file sits AT the package root (rel path is just
#                          the basename, e.g. "AGENTS.md"). An agent invoked with
#                          that package as CWD, or a tool that scans package roots,
#                          would discover it. This is the honest positive.
#   DEEP_UNVERIFIED      : the file is buried below the package root (rel has
#                          subdirectories). Discovery is possible but NOT
#                          documented/default; we do not claim reachability.
#
# This mirrors resolve.py's philosophy: verdicts describe DOCUMENTED behaviour,
# never observed loading.
# ---------------------------------------------------------------------------

INSTRUCTION_BASENAMES = {
    "AGENTS.md", "AGENT.md", "AGENTS.override.md", "CLAUDE.md", "CLAUDE.local.md",
    "GEMINI.md", ".cursorrules", ".clinerules", ".goosehints", "CONVENTIONS.md",
    ".windsurfrules",
}


def reachability_verdict(rel_within_pkg: str) -> str:
    """rel_within_pkg is the path BELOW the package root."""
    rel = rel_within_pkg.strip("/")
    # file directly at the package root => basename only, no slash
    if "/" not in rel:
        return "DOCUMENTED_REACHABLE"
    return "DEEP_UNVERIFIED"


# ---------------------------------------------------------------------------
# Load inputs
# ---------------------------------------------------------------------------


def load_carriage(results_dir: Path) -> dict[str, list[dict]]:
    """Return {ecosystem: [deduped records]} from carriage-*.jsonl."""
    out: dict[str, list[dict]] = {}
    for f in sorted(results_dir.glob("carriage-*.jsonl")):
        eco = f.stem.replace("carriage-", "")
        seen: dict[str, dict] = {}
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen[r["repo"]] = r  # last-wins dedupe
        out[eco] = list(seen.values())
    return out


def load_codeowners_gap(records_dir: Path) -> dict[str, bool]:
    """Return {repo: has_codeowners} from the RQ2 survey records.

    Reads survey/out/records-active-*.jsonl. The record field 'codeownersPath'
    is null when the repo has no CODEOWNERS file (ungoverned).
    """
    gov: dict[str, bool] = {}
    for f in sorted(records_dir.glob("records-active-*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            repo = r.get("repo")
            if repo:
                gov[repo] = bool(r.get("codeownersPath"))
    return gov


# ---------------------------------------------------------------------------
# The analysis
# ---------------------------------------------------------------------------

RESOLVED_STATES = {"success", "committed"}  # go uses "committed", others "success"


def analyse(rq3: dict[str, list[dict]], gov: dict[str, bool]) -> dict:
    per_eco = {}
    # global accumulators for the W headline
    all_carrier_repos = []          # (repo, eco) with >=1 third-party carried file
    tp_carrier_repos = set()        # repos with >=1 THIRD-PARTY carried file
    ungoverned_tp_carrier = set()   # + no CODEOWNERS
    reachable_tp_carrier = set()    # + >=1 DOCUMENTED_REACHABLE third-party file

    for eco, recs in sorted(rq3.items()):
        resolved = [r for r in recs if r.get("status") in RESOLVED_STATES]
        carriers = [r for r in resolved if r.get("carriedCount", 0) > 0]

        tp_files = 0                 # third-party carried files
        self_files = 0               # files not under the vendor prefix (rare)
        tp_packages = set()          # distinct third-party packages carrying
        reachable_files = 0
        deep_files = 0
        eco_tp_carrier_repos = set()
        eco_reachable_repos = set()

        for r in carriers:
            repo = r["repo"]
            repo_has_tp = False
            repo_has_reachable = False
            for cf in r.get("carriedInstructionFiles", []):
                parsed = parse_carried(eco, cf["path"])
                if parsed is None:
                    self_files += 1
                    continue
                pkg, rel = parsed
                tp_files += 1
                tp_packages.add((eco, pkg))
                repo_has_tp = True
                verdict = reachability_verdict(rel)
                if verdict == "DOCUMENTED_REACHABLE":
                    reachable_files += 1
                    repo_has_reachable = True
                else:
                    deep_files += 1
            if repo_has_tp:
                eco_tp_carrier_repos.add(repo)
                tp_carrier_repos.add(repo)
                all_carrier_repos.append((repo, eco))
                # governance: default to ungoverned if repo absent from RQ2 join
                has_co = gov.get(repo, False)
                if not has_co:
                    ungoverned_tp_carrier.add(repo)
                if repo_has_reachable:
                    eco_reachable_repos.add(repo)
                    reachable_tp_carrier.add(repo)

        n_res = len(resolved)
        n_tp_carrier = len(eco_tp_carrier_repos)
        per_eco[eco] = {
            "resolved": n_res,
            "carrierReposAny": len(carriers),
            "carrierReposThirdParty": n_tp_carrier,
            "carriageThirdPartyPct": wilson(n_tp_carrier, n_res),
            "thirdPartyCarriedFiles": tp_files,
            "selfOrUnrecognisedFiles": self_files,
            "distinctThirdPartyPackages": len({p for (e, p) in tp_packages if e == eco}),
            "reachability": {
                "documentedReachableFiles": reachable_files,
                "deepUnverifiedFiles": deep_files,
                "reachableSharePct": wilson(reachable_files, reachable_files + deep_files),
                "carrierReposWithReachableFile": len(eco_reachable_repos),
            },
            # governance per ecosystem
            "governance": {
                "thirdPartyCarrierRepos": n_tp_carrier,
                "ungovernedThirdPartyCarrierRepos": len(
                    {rp for rp in eco_tp_carrier_repos if not gov.get(rp, False)}),
            },
        }

    # ---- W: the headline intersection across all ecosystems ----
    W = len(tp_carrier_repos & ungoverned_tp_carrier & reachable_tp_carrier)
    total_tp_carriers = len(tp_carrier_repos)
    headline = {
        "thirdPartyCarrierReposTotal": total_tp_carriers,
        "ungovernedShare": {
            "count": len(tp_carrier_repos & ungoverned_tp_carrier),
            "of": total_tp_carriers,
            "pct": wilson(len(tp_carrier_repos & ungoverned_tp_carrier), total_tp_carriers),
        },
        "reachableShare": {
            "count": len(tp_carrier_repos & reachable_tp_carrier),
            "of": total_tp_carriers,
            "pct": wilson(len(tp_carrier_repos & reachable_tp_carrier), total_tp_carriers),
        },
        "W_thirdParty_AND_ungoverned_AND_reachable": {
            "count": W,
            "of": total_tp_carriers,
            "pct": wilson(W, total_tp_carriers),
        },
    }
    return {"perEcosystem": per_eco, "headline": headline}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="research/carriage-study/results",
                    help="dir with carriage-*.jsonl")
    ap.add_argument("--records", default="survey/out",
                    help="dir with records-active-*.jsonl (RQ2 CODEOWNERS signal)")
    ap.add_argument("--out", default="research/carriage-study/results/carriage-results.json")
    args = ap.parse_args()

    results_dir = Path(args.results)
    records_dir = Path(args.records)

    rq3 = load_carriage(results_dir)
    if not rq3:
        raise SystemExit(f"no carriage-*.jsonl found under {results_dir}")
    gov = load_codeowners_gap(records_dir)

    report = analyse(rq3, gov)
    report["_meta"] = {
        "codeownersRecordsLoaded": len(gov),
        "note": "the carriage study-B provenance, the carriage study-C governance join, the carriage study-D documented reachability. "
                "No file was executed or loaded; D reports documented discovery only.",
    }

    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # ---- human-readable summary ----
    print(f"\nRQ3-B/C/D  (CODEOWNERS records loaded: {len(gov)})\n")
    print(f"{'eco':8} {'resolved':>8} {'tp-carriers':>12} {'carriage%':>10} "
          f"{'tp-pkgs':>8} {'reachable':>10} {'deep':>6}")
    for eco, d in report["perEcosystem"].items():
        print(f"{eco:8} {d['resolved']:>8} {d['carrierReposThirdParty']:>12} "
              f"{d['carriageThirdPartyPct'][0]:>9}% {d['distinctThirdPartyPackages']:>8} "
              f"{d['reachability']['documentedReachableFiles']:>10} "
              f"{d['reachability']['deepUnverifiedFiles']:>6}")
    h = report["headline"]
    print("\n--- HEADLINE (across all ecosystems) ---")
    print(f"third-party carrier repos:        {h['thirdPartyCarrierReposTotal']}")
    print(f"  ...ungoverned (no CODEOWNERS):  {h['ungovernedShare']['count']} "
          f"({h['ungovernedShare']['pct'][0]}%)")
    print(f"  ...with a reachable file:       {h['reachableShare']['count']} "
          f"({h['reachableShare']['pct'][0]}%)")
    w = h["W_thirdParty_AND_ungoverned_AND_reachable"]
    print(f"  W = third-party ∩ ungoverned ∩ reachable: {w['count']}/{w['of']} "
          f"({w['pct'][0]}%)")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
