#!/usr/bin/env python3
"""Draw the repository sample, once, reproducibly, and freeze it.

This is genuine random sampling, not "the first N search results". It builds a
candidate frame, records every candidate ID and a checksum of the frame, seeds a
PRNG with a value you commit, and draws without replacement. The activity window
is computed from a snapshot date, not hard-coded, so the frozen protocol and the
code agree.

    python survey/sample.py --stratum active --language python \
        --snapshot 2026-08-15 --window-days 90 --n 500 --seed 20260815 \
        --out survey/out/sample-active-python.json

Everything needed to reproduce the draw is written into the output file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path

try:
    import httpx
except ModuleNotFoundError:
    sys.exit("survey needs httpx: pip install 'ovrin[survey]'")

API = "https://api.github.com"


def client() -> httpx.Client:
    h = {"Accept": "application/vnd.github+json", "User-Agent": "ovrin-survey/0.1"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok}"
    else:
        print("warning: no GITHUB_TOKEN, rate limit is 60/hour", file=sys.stderr)
    return httpx.Client(headers=h, timeout=30.0, follow_redirects=True)


def cutoff(snapshot: str, window_days: int) -> str:
    d = dt.date.fromisoformat(snapshot) - dt.timedelta(days=window_days)
    return d.isoformat()


def is_code_stratum(stratum: str) -> bool:
    # These need GitHub CODE search (filename:/path: qualifiers); repository
    # search silently ignores those qualifiers.
    return stratum in ("hasfile", "hasmcp")


def query_for(stratum: str, language: str | None, since: str) -> str:
    if stratum == "top":
        q = "stars:>1000"
    elif stratum == "active":
        q = f"pushed:>{since} stars:>10"
    elif stratum == "hasfile":
        q = "filename:AGENTS.md"       # CODE search: repos carrying an instruction file
    elif stratum == "hasmcp":
        q = "filename:.mcp.json"       # CODE search: repos carrying executing MCP config
    else:
        raise ValueError(stratum)
    return q + (f" language:{language}" if language else "")


def build_frame(c: httpx.Client, q: str, cap: int, code: bool = False) -> list[dict]:
    """Collect a candidate frame. GitHub search returns at most 1000 results per
    query, so for a broad frame we page to the cap and treat that as the frame.
    Every candidate is recorded, so the frame is reproducible and auditable.

    code=True uses the CODE search endpoint (for filename:/path: strata) and
    dedupes to repositories; its items carry a minimal 'repository' sub-object
    and a stricter rate limit, so we page more slowly. Code-search repo objects
    omit stars/pushed/default_branch, so those are recorded as None and the
    crawler falls back to the 'main' branch."""
    endpoint = "/search/code" if code else "/search/repositories"
    params_extra = {} if code else {"sort": "updated"}
    frame, page, seen = [], 1, set()
    while len(frame) < cap and page <= 10:
        r = c.get(f"{API}{endpoint}",
                  params={"q": q, "per_page": 100, "page": page, **params_extra})
        if r.status_code in (403, 429) and r.headers.get("x-ratelimit-remaining") == "0":
            wait = max(0, int(r.headers.get("x-ratelimit-reset", 0)) - int(time.time())) + 2
            print(f"rate limited, sleeping {wait}s", file=sys.stderr)
            time.sleep(wait)
            continue
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            break
        for it in items:
            repo = it.get("repository", it) if code else it
            rid = repo.get("id")
            if rid is None or rid in seen:
                continue
            # Exclude forks, archived, mirrors, templates (when the object says so).
            if (repo.get("fork") or repo.get("archived")
                    or repo.get("mirror_url") or repo.get("is_template")):
                continue
            seen.add(rid)
            frame.append({"id": rid, "repo": repo["full_name"],
                          "stars": repo.get("stargazers_count"),
                          "language": repo.get("language"),
                          "pushedAt": repo.get("pushed_at"),
                          "defaultBranch": repo.get("default_branch"),
                          "fork": bool(repo.get("fork")),
                          "archived": bool(repo.get("archived")),
                          "isTemplate": bool(repo.get("is_template"))})
        page += 1
        time.sleep(6 if code else 2)  # code search limit is stricter (~10/min)
    return frame


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stratum", choices=("top", "active", "hasfile", "hasmcp"), required=True)
    ap.add_argument("--language", default=None)
    ap.add_argument("--snapshot", required=True, help="YYYY-MM-DD, the frozen snapshot date")
    ap.add_argument("--window-days", type=int, default=90)
    ap.add_argument("--n", type=int, default=500, help="sample size to draw from the frame")
    ap.add_argument("--frame-cap", type=int, default=1000, help="max candidates to collect")
    ap.add_argument("--seed", type=int, required=True,
                    help="PRNG seed, committed for reproducibility")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    since = cutoff(a.snapshot, a.window_days)
    q = query_for(a.stratum, a.language, since)

    with client() as c:
        frame = build_frame(c, q, a.frame_cap, code=is_code_stratum(a.stratum))

    if not frame:
        print("empty candidate frame", file=sys.stderr)
        return 1

    # Reproducible draw without replacement.
    ids = sorted(f["id"] for f in frame)
    frame_checksum = hashlib.sha256(json.dumps(ids).encode()).hexdigest()
    rng = random.Random(a.seed)
    n = min(a.n, len(frame))
    chosen_ids = set(rng.sample(ids, n))
    sample = [f for f in frame if f["id"] in chosen_ids]
    for s in sample:
        s["stratum"] = a.stratum

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "protocol": "ovrin-research-v1.0",
        "stratum": a.stratum,
        "language": a.language,
        "snapshotDate": a.snapshot,
        "activityWindowDays": a.window_days,
        "activityCutoff": since,
        "query": q,
        "frameSize": len(frame),
        "frameCap": a.frame_cap,
        "frameRepositoryIds": sorted(f["id"] for f in frame),
        "frameDescription": ("reproducible random sample from a pre-defined active "
                             "GitHub search frame; forks, archived, mirrors and "
                             "templates excluded. NOT an unbiased base rate of all GitHub."),
        "exclusions": ["fork", "archived", "mirror", "template"],
        "frameChecksum": f"sha256:{frame_checksum}",
        "seed": a.seed,
        "drawn": n,
        "sample": sample,
    }, indent=2), encoding="utf-8")

    print(f"frame={len(frame)}  drawn={n}  seed={a.seed}", file=sys.stderr)
    print(f"query: {q}", file=sys.stderr)
    print(f"wrote {out}  (commit this file)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
