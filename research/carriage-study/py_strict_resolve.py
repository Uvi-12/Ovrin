#!/usr/bin/env python3
"""Strict Python dependency resolver (runs INSIDE the container).
Lockfiles + requirements only. Emits a flat pinned list to _reqs.txt.
Exits 66 if no lock/requirements found, 0 on success. Prints ROUTE=<file> and
COHORT=<locked|unpinned> to stderr for provenance. Does NOT download or build
anything itself — it only reads manifest files as static data (TOML / text).

Cohort classification (reviewer point 2):
  LOCKED   = uv.lock / poetry.lock / pdm.lock  (fully pinned transitive tree)
  UNPINNED = requirements*.txt / requirements.in  (may miss transitive deps)
The headline the carriage study-A should use the LOCKED cohort; UNPINNED is exploratory.

Requirements precedence (reviewer point 3): explicit order, not lexical sort,
so requirements-dev.txt never shadows requirements.txt.
"""
import os, sys, glob
try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None


def lockpkgs(path):
    d = tomllib.load(open(path, "rb"))
    out = []
    for x in d.get("package", []):
        n, v = x.get("name"), x.get("version")
        # Exclude the local/workspace project itself (source = editable/directory/
        # path/virtual). The other ecosystems (cargo vendor, npm ci) structurally
        # exclude the root package; this keeps Python consistent and prevents a
        # local package name from being resolved to an unrelated PyPI distribution.
        src = x.get("source", {})
        if isinstance(src, dict) and any(k in src for k in ("editable", "directory", "path", "virtual")):
            continue
        if n and v:
            out.append(f"{n}=={v}")
    return out


def read_reqs(path):
    return [l.strip() for l in open(path)
            if l.strip() and not l.strip().startswith(("#", "-"))]


route, reqs, cohort = None, [], None

# LOCKED cohort: fully-pinned lockfiles (highest priority)
if tomllib and os.path.exists("uv.lock"):
    route, reqs, cohort = "uv.lock", lockpkgs("uv.lock"), "locked"
elif tomllib and os.path.exists("poetry.lock"):
    route, reqs, cohort = "poetry.lock", lockpkgs("poetry.lock"), "locked"
elif tomllib and os.path.exists("pdm.lock"):
    route, reqs, cohort = "pdm.lock", lockpkgs("pdm.lock"), "locked"
else:
    # UNPINNED cohort: explicit precedence, NOT lexical glob sort
    PRECEDENCE = ["requirements.txt", "requirements.lock", "requirements.in",
                  "requirements-prod.txt", "requirements-dev.txt"]
    chosen = None
    for cand in PRECEDENCE:
        if os.path.exists(cand):
            chosen = cand
            break
    if chosen is None:
        # any other requirements*.txt as last resort, deterministic order
        rest = sorted(glob.glob("requirements*.txt"))
        chosen = rest[0] if rest else None
    if chosen:
        route, reqs, cohort = chosen, read_reqs(chosen), "unpinned"

if not route or not reqs:
    sys.exit(66)
open("_reqs.txt", "w").write("\n".join(reqs))
# provenance to stderr (drive.py can capture); COHORT distinguishes headline vs exploratory
sys.stderr.write(f"ROUTE={route} COHORT={cohort} PKGS={len(reqs)}\n")
