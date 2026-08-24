#!/usr/bin/env python3
"""the carriage study safe container harness (disk-light): materialize a repo's dependency tree
without executing dependency code, extracting only instruction files + provenance
metadata so the host never stores a full node_modules/vendor tree.

Two paths:
  - Go committed vendor: the vendor tree is already in the clone after checkout.
    No container, no copy. The caller scans it in place. (run() returns a marker.)
  - npm / cargo / python / maven: the container does all writing on its own layer
    (copied to /work inside the container, which lives on Docker's disk, not the
    host repo dir). We then list the materialized tree from inside the container
    and print out ONLY recognized instruction files + their SHA256.

The host repo dir is mounted READ-ONLY. Nothing large is copied to host disk.

Safety guarantee (no dependency code execution):
  - npm:    npm ci --ignore-scripts            (lifecycle scripts disabled)
  - cargo:  cargo vendor --locked              (copies sources, no build)
  - python: pip download --no-deps             (fetches wheels AND sdists but
            builds NOTHING; --no-deps prevents any build-for-metadata step since
            the lockfile is already fully resolved), then archives are UNPACKED
            (tar/zip) which runs no package code.
  - maven:  mvn dependency:go-offline          (resolves archives to cache)
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

INSTRUCTION_BASENAMES = {
    "AGENTS.md", "AGENTS.override.md", "AGENT.md", "CLAUDE.md", "CLAUDE.local.md",
    "GEMINI.md", ".cursorrules", ".clinerules", ".goosehints", "CONVENTIONS.md",
    ".windsurfrules",
}

ECOSYSTEMS = {
    "go": {"image": "golang:1.23", "vendor_subdir": "vendor", "committed": True},
    "npm": {"image": "node:22", "vendor_subdir": "node_modules", "committed": False,
            "resolve": "if [ -f package-lock.json ]; then npm ci --ignore-scripts >/dev/null 2>&1 || exit 70; else exit 66; fi"},
    "cargo": {"image": "rust:1.83", "vendor_subdir": "_v", "committed": False,
              "resolve": "export PATH=/usr/local/cargo/bin:$PATH; if [ -f Cargo.lock ]; then cargo vendor --locked _v >/dev/null 2>&1 || exit 70; else exit 66; fi"},
    "python": {"image": "python:3.13", "vendor_subdir": "_s", "committed": False,
               "resolve": "python3 /py_strict_resolve.py; rc=$?; [ $rc -eq 66 ] && exit 66; [ $rc -ne 0 ] && exit 70; python -m pip download --no-deps -r _reqs.txt -d _w >/dev/null 2>&1 || exit 70; mkdir -p _s; ( cd _w && for f in *.whl *.zip; do [ -e \"$f\" ] || continue; python -m zipfile -e \"$f\" ../_s/ 2>/dev/null; done; for f in *.tar.gz *.tgz; do [ -e \"$f\" ] || continue; tar xzf \"$f\" -C ../_s/ 2>/dev/null; done ) || true"},
    "maven": {"image": "maven:3.9-eclipse-temurin-21", "vendor_subdir": "_m2", "committed": False,
              "resolve": "[ -f pom.xml ] || exit 66; mvn -q dependency:go-offline -Dmaven.repo.local=_m2 >/dev/null 2>&1 || exit 70"},
}

FIND_INSTR = (
    'find "{sub}" -type f \\( '
    '-name AGENTS.md -o -name AGENTS.override.md -o -name AGENT.md '
    '-o -name CLAUDE.md -o -name CLAUDE.local.md -o -name GEMINI.md '
    '-o -name .cursorrules -o -name .clinerules -o -name .goosehints '
    '-o -name CONVENTIONS.md -o -name .windsurfrules '
    '-o -path "*/.cursor/rules/*" -o -path "*/.claude/rules/*" '
    '-o -path "*/.windsurf/rules/*" \\) 2>/dev/null | while read f; do '
    'printf "%s\\t%s\\n" "$(sha256sum "$f" | cut -d" " -f1)" "$f"; done'
)

_PROBE = {"go": ["go", "version"], "npm": ["npm", "--version"],
          "cargo": ["cargo", "--version"], "python": ["python", "--version"],
          "maven": ["mvn", "--version"]}


def _tool_version(image: str, probe: list[str]) -> str:
    try:
        p = subprocess.run(["docker", "run", "--rm", image, *probe],
                          capture_output=True, text=True, timeout=60, check=False)
        return (p.stdout or p.stderr).strip().split("\n")[0]
    except Exception:
        return "unknown"


def run(repo_dir: Path, ecosystem: str, out_dir: Path, timeout: int = 600) -> dict:
    spec = ECOSYSTEMS[ecosystem]
    out_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()

    if spec["committed"]:
        vend = repo_dir / spec["vendor_subdir"]
        return {"ecosystem": ecosystem, "mode": "committed-vendor",
                "status": "committed" if vend.exists() else "no-vendor",
                "vendorSubdir": spec["vendor_subdir"],
                "toolVersion": "n/a (committed vendor)",
                "elapsedSeconds": round(time.time() - started, 1)}

    sub = spec["vendor_subdir"]
    script = ("cp -a /src /work && cd /work && " + spec["resolve"] + " && "
              + FIND_INSTR.format(sub=sub))
    docker_cmd = [
        "docker", "run", "--rm", "--memory", "3g", "--cpus", "2",
        "-v", f"{repo_dir.resolve()}:/src:ro",
        "-v", f"{Path(__file__).resolve().parent / 'py_strict_resolve.py'}:/py_strict_resolve.py:ro",
        spec["image"], "bash", "-lc", script,
    ]
    try:
        p = subprocess.run(docker_cmd, capture_output=True, text=True,
                          timeout=timeout, check=False)
        rc, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return {"ecosystem": ecosystem, "mode": "resolver", "status": "timeout",
                "elapsedSeconds": round(time.time() - started, 1)}

    status = {0: "success", 66: "no-manifest-or-lockfile",
              70: "resolve-failed"}.get(rc, f"error-{rc}")
    carried = []
    if rc == 0:
        for line in out.strip().splitlines():
            if "\t" in line:
                sha, path = line.split("\t", 1)
                carried.append({"sha256": sha, "path": path})
    return {
        "ecosystem": ecosystem, "mode": "resolver", "status": status,
        "resolveReturncode": rc,
        "toolVersion": _tool_version(spec["image"], _PROBE[ecosystem]),
        "vendorSubdir": sub, "carried": carried,
        "elapsedSeconds": round(time.time() - started, 1),
        "stderrTail": err[-800:],
    }
