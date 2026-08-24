#!/usr/bin/env python3
"""the carriage study: resolve a repository's dependency tree without executing it, find
instruction files that arrived from outside the project, and run each one
through the real harness reachability engine.

YOU RUN THIS in a container or throwaway VM. It never runs install scripts, so a
malicious package cannot execute during resolution.

Only npm and Go are supported, because only they materialise a scannable
dependency tree under the repository (node_modules/, vendor/). pip and cargo
place files in caches or archives that need extraction first, so they would
silently return zero and are deliberately not offered.

    python research/reachability/resolve.py --repo owner/name --ecosystem npm \
        --out research/reachability/results/owner-name.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from ovrin.harness import Rules, reachability  # noqa: E402
from ovrin.survey_probe import instruction_paths_in  # noqa: E402

# Only ecosystems that put a scannable tree under the repo. Install scripts off.
RESOLVE = {
    "npm": (["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"], "node_modules"),
    "go": (["go", "mod", "vendor"], "vendor"),
}


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600, check=False)
        return p.returncode, (p.stderr or "")[-2000:]
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def clone(repo: str, dest: Path) -> bool:
    url = f"https://github.com/{repo}"
    rc, _ = run(["git", "clone", "--depth", "1", url, str(dest)], dest.parent)
    return rc == 0

def git_ignored(work: Path, rel: str) -> bool:
    """Ask git whether this path is actually ignored, instead of assuming."""
    p = subprocess.run(["git", "check-ignore", "-q", rel], cwd=work, check=False)
    return p.returncode == 0
def git_tracked(work: Path, rel: str) -> bool:
    """Ask git whether this path is actually tracked (committed)."""
    p = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                       cwd=work, capture_output=True, check=False)
    return p.returncode == 0
def classify_carrier(work: Path, rel: str) -> tuple[str, bool]:
    """Return (origin_cls, is_ignored) from real git state, not a guess.
    A committed vendor tree (Go vendor/) is 'vendored' and not ignored; an
    installed, git-ignored tree (npm node_modules) is 'installed-dependency'."""
    ignored = git_ignored(work, rel)
    tracked = git_tracked(work, rel)
    if tracked:
        return "vendored", False
    if ignored:
        return "installed-dependency", True
    return "installed-dependency", ignored

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--ecosystem", choices=list(RESOLVE), required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    cmd, vendor_dir = RESOLVE[a.ecosystem]
    result = {"repo": a.repo, "ecosystem": a.ecosystem, "installScriptsDisabled": True,
              "resolveCommand": " ".join(cmd), "vendorDir": vendor_dir}
    rules = Rules.load()

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        work.mkdir(parents=True)
        if not clone(a.repo, work):
            result["status"] = "clone-failed"
            _write(a.out, result)
            return 1

        rc, err = run(cmd, work)
        result["resolveReturncode"] = rc
        if rc != 0:
            result["status"] = "resolve-failed"
            result["resolveError"] = err
            _write(a.out, result)
            return 0  # a failed resolution is data, not a crash

        vroot = work / vendor_dir
        all_paths = ([str(p.relative_to(work)) for p in vroot.rglob("*") if p.is_file()]
                     if vroot.exists() else [])
        instr = instruction_paths_in(all_paths)
        carried = [i for i in instr if i["path"].startswith(vendor_dir + "/")]

        # Feed each carrier through the real reachability engine, per harness.
        # Origin and ignore status come from real git state, not a guess: a
        # committed vendor tree (Go) is 'vendored' and not ignored, an installed
        # tree (npm node_modules) is 'installed-dependency' and ignored.
        # active_path is the carrier's own directory: we ask whether the file is
        # reachable for an agent working where that dependency lives.
        analysed = []
        for c in carried:
            origin_cls, is_ignored = classify_carrier(work, c["path"])
            active = c["path"].rsplit("/", 1)[0] if "/" in c["path"] else ""
            per_harness = {}
            for h in rules.harnesses:
                verdict, reason = reachability(
                    h, c["path"], is_ignored=is_ignored, origin_cls=origin_cls,
                    active_path=active)
                if verdict == "not-discovered":
                    continue
                per_harness[h.id] = {"verdict": verdict, "reason": reason,
                                     "confidence": h.confidence}
            analysed.append({**c, "origin": origin_cls, "isIgnored": is_ignored,
                             "activePath": active, "reachability": per_harness})

        result["status"] = "ok"
        result["vendorTreeFiles"] = len(all_paths)
        result["externallyCarried"] = len(carried)
        result["carried"] = analysed
        # summary: how many carriers are 'loaded' vs 'unverified' by >=1 harness
        result["carriersReachableBySomeHarness"] = sum(
            1 for c in analysed
            if any(r["verdict"] == "loaded" for r in c["reachability"].values()))
        result["carriersUnverifiedOnly"] = sum(
            1 for c in analysed
            if c["reachability"]
            and all(r["verdict"] == "unverified" for r in c["reachability"].values()))

    _write(a.out, result)
    print(json.dumps({k: result[k] for k in
                      ("repo", "status", "externallyCarried", "carriersReachableBySomeHarness")
                      if k in result}), file=sys.stderr)
    return 0


def _write(out: str, data: dict) -> None:
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
