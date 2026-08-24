#!/usr/bin/env python3
"""the carriage study Phase 2 driver (disk-light, one repo at a time): for each repo in a frozen
sample, full-checkout at HEAD, resolve/scan for carried instruction files, write
one JSONL record, then DELETE the clone before the next repo. Peak disk = 1 repo.

    python research/carriage-study/drive.py \
        --sample survey/out/sample-active-go.json \
        --ecosystem go \
        --out research/carriage-study/results/carriage-go.jsonl

Resumable: repos already in the output are skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_in_container import run as harness_run, INSTRUCTION_BASENAMES  # noqa: E402

MANIFESTS = {
    "go": ["go.mod"], "npm": ["package-lock.json"], "cargo": ["Cargo.lock"],
    "python": ["uv.lock", "poetry.lock", "pdm.lock", "requirements.txt",
               "requirements-dev.txt", "requirements.in"],
    "maven": ["pom.xml"],
}


def clone_head(repo: str, branch: str, dest: Path) -> str | None:
    url = f"https://github.com/{repo}.git"
    ok = subprocess.run(["git", "clone", "--depth", "1", "--branch", branch,
                        "--single-branch", url, str(dest)],
                       capture_output=True, text=True, check=False).returncode == 0
    if not ok:
        ok = subprocess.run(["git", "clone", "--depth", "1", url, str(dest)],
                          capture_output=True, text=True, check=False).returncode == 0
        if not ok:
            return None
    sha = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"],
                       capture_output=True, text=True, check=False)
    return sha.stdout.strip() or None


def scan_go_vendor(repo_dir: Path, subdir: str) -> list[dict]:
    root = repo_dir / subdir
    if not root.exists():
        return []
    out = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(repo_dir))
        hit = (p.name in INSTRUCTION_BASENAMES
               or "/.cursor/rules/" in "/" + rel
               or "/.claude/rules/" in "/" + rel
               or "/.windsurf/rules/" in "/" + rel)
        if hit:
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            out.append({"sha256": sha, "path": rel})
    return out


def done_repos(out_path: Path) -> set:
    if not out_path.exists():
        return set()
    s = set()
    for line in out_path.open():
        try:
            s.add(json.loads(line)["repo"])
        except Exception:
            pass
    return s


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", required=True)
    ap.add_argument("--ecosystem", choices=list(MANIFESTS), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=600)
    a = ap.parse_args()

    sample = json.load(open(a.sample))["sample"]
    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    already = done_repos(out_path)
    attempted = 0

    with out_path.open("a") as out:
        for entry in sample:
            repo = entry["repo"]
            if repo in already:
                continue
            if a.limit and attempted >= a.limit:
                break
            attempted += 1
            rec = {"repo": repo, "ecosystem": a.ecosystem}
            tmp = Path(tempfile.mkdtemp(prefix="carriage-"))
            try:
                dest = tmp / "repo"
                sha = clone_head(repo, entry.get("defaultBranch") or "main", dest)
                if sha is None:
                    rec["status"] = "clone-failed"
                    out.write(json.dumps(rec) + "\n"); out.flush()
                    print(f"{repo}: clone-failed"); continue
                rec["commit"] = sha
                if not any((dest / m).exists() for m in MANIFESTS[a.ecosystem]):
                    rec["status"] = "no-manifest"
                    out.write(json.dumps(rec) + "\n"); out.flush()
                    print(f"{repo}: no-manifest"); continue
                res = harness_run(dest, a.ecosystem, tmp / "out", a.timeout)
                if res.get("mode") == "committed-vendor":
                    carried = scan_go_vendor(dest, res["vendorSubdir"]) \
                        if res["status"] == "committed" else []
                    rec["status"] = res["status"]
                else:
                    carried = res.get("carried", [])
                    rec["status"] = res["status"]
                rec["resolution"] = {k: res.get(k) for k in
                    ("mode", "status", "toolVersion", "elapsedSeconds")}
                rec["carriedInstructionFiles"] = carried
                rec["carriedCount"] = len(carried)
                out.write(json.dumps(rec) + "\n"); out.flush()
                print(f"{repo}: {rec['status']} carried={rec['carriedCount']} "
                      f"({res.get('elapsedSeconds')}s)")
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
    print(f"\ndone. attempted {attempted} new repos, wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
