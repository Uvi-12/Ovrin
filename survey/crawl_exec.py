#!/usr/bin/env python3
"""Inspect every repository in a frozen sample for EXECUTING agent config.

The executing-surface analog of crawl.py. Reads the SAME sample file produced by
sample.py (never draws its own), pulls each repo's tree once, finds every
executing config (MCP servers, hooks, skills) with exec_probe, fetches just
those config files to read their declared capabilities, and tests each config
path against the repo's CODEOWNERS with the SAME matcher the scanner and the
instruction survey use (coverage_for). Truncated trees are recorded and excluded
from prevalence, never counted as a clean negative.

    python survey/crawl_exec.py --sample survey/out/sample-active-python.json \
        --out survey/out/exec-active-python.jsonl
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

try:
    import httpx
except ModuleNotFoundError:
    sys.exit("survey needs httpx: pip install 'ovrin[survey]'")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # the ovrin package
sys.path.insert(0, str(Path(__file__).resolve().parent))                 # exec_probe (same dir)
from ovrin.codeowners import LOCATIONS as CODEOWNERS_LOCATIONS  # noqa: E402
from ovrin.survey_probe import coverage_for  # noqa: E402  (same matcher as instruction survey)
import exec_probe  # noqa: E402

API = "https://api.github.com"


def client() -> httpx.Client:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "ovrin-exec-survey/0.1"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    else:
        print("warning: no GITHUB_TOKEN, rate limit is 60/hour", file=sys.stderr)
    return httpx.Client(headers=h, timeout=30.0, follow_redirects=True)


def get(c: httpx.Client, url: str, **params):
    for _ in range(4):
        r = c.get(url, params=params or None)
        if r.status_code == 403 and r.headers.get("x-ratelimit-remaining") == "0":
            wait = max(0, int(r.headers.get("x-ratelimit-reset", 0)) - int(time.time())) + 2
            print(f"rate limited, sleeping {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        if r.status_code == 404:
            return None
        if r.status_code >= 500:
            time.sleep(3)
            continue
        r.raise_for_status()
        return r.json()
    return None


def full_tree(c, full, branch):
    data = get(c, f"{API}/repos/{full}/git/trees/{branch}", recursive="1")
    if not data:
        return [], False
    truncated = bool(data.get("truncated"))
    return [e["path"] for e in data.get("tree", []) if e.get("type") == "blob"], truncated


def file_text(c, full, path):
    meta = get(c, f"{API}/repos/{full}/contents/{path}")
    if isinstance(meta, dict) and meta.get("content"):
        try:
            return base64.b64decode(meta["content"]).decode("utf-8", errors="replace")
        except (ValueError, KeyError):
            return None
    return None


def codeowners_from_tree(c, full, pathset):
    for loc in CODEOWNERS_LOCATIONS:
        if loc in pathset:
            t = file_text(c, full, loc)
            return t, loc, True
    return None, None, False


def probe(c, entry):
    full = entry["repo"]
    branch = entry.get("defaultBranch") or "main"
    rec = dict(entry)
    paths, truncated = full_tree(c, full, branch)
    rec["treeSize"] = len(paths)
    rec["treeTruncated"] = truncated
    if not paths:
        rec["crawlStatus"] = "empty-or-error"
        rec["execConfigs"] = []
        rec["hasExec"] = False
        return rec
    if truncated:
        rec["crawlStatus"] = "truncated"
        rec["execConfigs"] = []
        rec["hasExec"] = None
        return rec

    pathset = set(paths)
    configs = exec_probe.exec_configs_in(paths)
    co_text, co_path, co_present = codeowners_from_tree(c, full, pathset) if configs else (None, None, False)
    rec["codeownersPath"] = co_path

    enriched = []
    for cfg in configs:
        cov = coverage_for(co_text, co_path, cfg["path"], codeowners_present=co_present)
        caps = []
        if cfg["kind"] in ("mcp", "hooks"):
            caps = exec_probe.caps_for(cfg["kind"], file_text(c, full, cfg["path"]))
        enriched.append({**cfg, **cov, "capabilities": caps})

    rec["execConfigs"] = enriched
    rec["hasExec"] = any(c["autoExec"] for c in enriched)
    rec["crawlStatus"] = "ok"
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    doc = json.loads(Path(a.sample).read_text(encoding="utf-8"))
    sample = doc["sample"]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Resume: skip repositories already recorded in the output file. A big,
    # rate-limited sweep WILL pause; re-running continues exactly where it
    # stopped. Delete the output file to start fresh.
    done: set[str] = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    done.add(json.loads(line)["repo"])
                except (ValueError, KeyError):
                    pass
    todo = [e for e in sample if e["repo"] not in done]
    if done:
        print(f"  resuming: {len(done)} already done, {len(todo)} to go", file=sys.stderr)

    with client() as c, out.open("a", encoding="utf-8") as fh:
        for i, entry in enumerate(todo, 1):
            try:
                rec = probe(c, entry)
            except Exception as e:  # noqa: BLE001 — one bad repo must never abort the sweep
                rec = {**entry, "crawlStatus": "error",
                       "crawlError": f"{type(e).__name__}: {e}",
                       "execConfigs": [], "hasExec": None}
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if i % 10 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}  (+{len(done)} done)", file=sys.stderr)

    print(f"wrote {out}  ({len(done) + len(todo)} repositories total)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
