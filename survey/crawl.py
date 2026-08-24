#!/usr/bin/env python3
"""Inspect every repository in a frozen sample and record what it carries.

Reads a sample file from sample.py and never draws its own. For each repository
it pulls the full tree recursively, matches every path against the SAME
formats.yaml the scanner uses, finds the CODEOWNERS from that same tree, and
tests each instruction path against it with the SAME matcher the scanner uses.

Truncated trees are recorded as such and excluded from prevalence, never
counted as a clean negative.

    python survey/crawl.py --sample survey/out/sample-active-python.json \
        --out survey/out/records-active-python.jsonl --history
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ovrin.codeowners import LOCATIONS as CODEOWNERS_LOCATIONS  # noqa: E402
from ovrin.survey_probe import coverage_for, instruction_paths_in  # noqa: E402

API = "https://api.github.com"


def client() -> httpx.Client:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "ovrin-survey/0.1"}
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


def full_tree(c: httpx.Client, full: str, branch: str) -> tuple[list[str], bool]:
    """Every blob path, and whether the API truncated the response."""
    data = get(c, f"{API}/repos/{full}/git/trees/{branch}", recursive="1")
    if not data:
        return [], False
    truncated = bool(data.get("truncated"))
    paths = [e["path"] for e in data.get("tree", []) if e.get("type") == "blob"]
    return paths, truncated


def codeowners_from_tree(
    c: httpx.Client, full: str, paths: set[str]
) -> tuple[str | None, str | None, bool]:
    """Find the CODEOWNERS in the tree we already have, then fetch only that one
    file. GitHub uses the first of these locations that exists."""
    for loc in CODEOWNERS_LOCATIONS:
        if loc in paths:
            meta = get(c, f"{API}/repos/{full}/contents/{loc}")
            if meta and isinstance(meta, dict) and meta.get("content"):
                try:
                    text = base64.b64decode(meta["content"]).decode("utf-8", errors="replace")
                    return text, loc, True
                except (ValueError, KeyError):
                    return None, loc, True
            return None, loc, True
    return None, None, False


def history(c: httpx.Client, full: str, path: str) -> dict:
    commits = get(c, f"{API}/repos/{full}/commits", path=path, per_page=100)
    if not commits:
        return {"commits": 0}
    authors = [(cm.get("author") or {}).get("login") for cm in commits if cm.get("author")]
    adding = commits[-1]
    return {
        "commits": len(commits),
        "distinctAuthors": sorted({a for a in authors if a}),
        "addedBy": (adding.get("author") or {}).get("login"),
        "firstDate": adding["commit"]["author"]["date"],
        "lastDate": commits[0]["commit"]["author"]["date"],
    }


def probe(c: httpx.Client, entry: dict, with_history: bool) -> dict:
    full = entry["repo"]
    branch = entry.get("defaultBranch") or "main"
    rec = dict(entry)

    paths, truncated = full_tree(c, full, branch)
    rec["treeSize"] = len(paths)
    rec["treeTruncated"] = truncated
    if not paths:
        rec["crawlStatus"] = "empty-or-error"
        rec["instructionFiles"] = []
        rec["hasInstructions"] = False
        return rec
    if truncated:
        # A truncated tree cannot be counted as a clean negative for prevalence.
        rec["crawlStatus"] = "truncated"
        rec["instructionFiles"] = []
        rec["hasInstructions"] = None
        return rec

    pathset = set(paths)
    co_text, co_path, co_present = codeowners_from_tree(c, full, pathset)
    rec["codeownersPath"] = co_path

    instr = instruction_paths_in(paths)
    files = []
    for it in instr:
        cov = coverage_for(co_text, co_path, it["path"], codeowners_present=co_present)
        entry_rec = {**it, **cov}
        if with_history:
            entry_rec["history"] = history(c, full, it["path"])
        files.append(entry_rec)

    rec["instructionFiles"] = files
    rec["hasInstructions"] = bool(files)
    rec["crawlStatus"] = "ok"
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sample", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--history", action="store_true")
    a = ap.parse_args()

    doc = json.loads(Path(a.sample).read_text(encoding="utf-8"))
    sample = doc["sample"]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with client() as c, out.open("w", encoding="utf-8") as fh:
        for i, entry in enumerate(sample, 1):
            try:
                rec = probe(c, entry, a.history)
            except httpx.HTTPError as e:
                rec = {**entry, "crawlStatus": "error", "crawlError": str(e),
                       "instructionFiles": [], "hasInstructions": None}
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if i % 25 == 0:
                print(f"  {i}/{len(sample)}", file=sys.stderr)

    print(f"wrote {out}  ({len(sample)} repositories)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
