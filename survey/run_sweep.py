#!/usr/bin/env python3
"""Orchestrate the ecosystem execution-config sweep from protocol.yaml.

For each sample in the protocol it draws a frozen sample once (sample.py; skipped
if the file already exists), crawls it for executing agent config (crawl_exec.py,
resumable), and finally analyses every exec record together (analyze_exec.py),
writing a report, a machine-readable analysis, and a provenance manifest.

Safe to re-run: frozen samples are not re-drawn, and a crawl that paused on a
rate limit continues where it stopped. This is the executing-surface analog of
the instruction survey and reuses the same sampler and CODEOWNERS matcher.

    python sweep/run_sweep.py --protocol protocol.yaml --out out
    python sweep/run_sweep.py --protocol protocol.yaml --out out --dry-run
    python sweep/run_sweep.py --out out --only-analyze
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _slug(stratum: str, language) -> str:
    return f"{stratum}-{language or 'any'}"


def _load_protocol(path: Path) -> dict:
    import yaml
    doc = yaml.safe_load(path.read_text("utf-8")) or {}
    doc.setdefault("snapshot", dt.date.today().isoformat())
    doc.setdefault("window_days", 90)
    doc.setdefault("seed_base", 1)
    doc.setdefault("frame_cap", 1000)
    doc.setdefault("samples", [])
    return doc


def _run(argv: list[str]) -> int:
    print(f"    $ {' '.join(argv)}", file=sys.stderr)
    return subprocess.run(argv, cwd=str(ROOT)).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--protocol", default="protocol.yaml")
    ap.add_argument("--out", default="out")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, touch nothing")
    ap.add_argument("--only-analyze", action="store_true", help="skip sample/crawl, just analyse out/")
    a = ap.parse_args()

    # paths resolve against this script's directory (survey/), not the repo root,
    # so `python survey/run_sweep.py` works from anywhere
    out = Path(a.out) if Path(a.out).is_absolute() else (HERE / a.out)
    out.mkdir(parents=True, exist_ok=True)
    proto = _load_protocol(Path(a.protocol) if Path(a.protocol).is_absolute() else (HERE / a.protocol))
    py = sys.executable

    plan = []
    for i, s in enumerate(proto["samples"]):
        slug = _slug(s["stratum"], s.get("language"))
        plan.append({
            "slug": slug, "stratum": s["stratum"], "language": s.get("language"),
            "n": int(s.get("n", 300)), "seed": int(proto["seed_base"]) + i,
            "sample": out / f"sample-{slug}.json",
            "records": out / f"exec-{slug}.jsonl",
        })

    if a.dry_run:
        print(f"snapshot={proto['snapshot']} window={proto['window_days']}d seed_base={proto['seed_base']}")
        for p in plan:
            have_s = "exists" if p["sample"].exists() else "to-draw"
            have_r = f"{sum(1 for _ in p['records'].open()) if p['records'].exists() else 0} done" \
                if p["records"].exists() else "none"
            print(f"  {p['slug']:<22} n={p['n']:<4} seed={p['seed']}  sample:{have_s}  records:{have_r}")
        return 0

    if not a.only_analyze:
        for p in plan:
            print(f"\n[{p['slug']}]", file=sys.stderr)
            # 1. draw the frozen sample once
            if p["sample"].exists():
                print("    sample frozen, skipping draw", file=sys.stderr)
            else:
                argv = [py, str(HERE / "sample.py"), "--stratum", p["stratum"],
                        "--snapshot", str(proto["snapshot"]), "--window-days", str(proto["window_days"]),
                        "--n", str(p["n"]), "--seed", str(p["seed"]),
                        "--frame-cap", str(proto["frame_cap"]), "--out", str(p["sample"])]
                if p["language"]:
                    argv += ["--language", p["language"]]
                if _run(argv) != 0 or not p["sample"].exists():
                    print(f"    ! sampling failed for {p['slug']} (check GITHUB_TOKEN / rate limit); "
                          f"skipping", file=sys.stderr)
                    continue
            # 2. crawl it for executing config (resumable)
            _run([py, str(HERE / "crawl_exec.py"), "--sample", str(p["sample"]),
                  "--out", str(p["records"])])

    # 3. analyse every exec record together
    record_files = sorted(str(p) for p in out.glob("exec-*.jsonl"))
    if not record_files:
        print("no exec-*.jsonl records to analyse yet", file=sys.stderr)
        return 1
    report = out / "report-exec.txt"
    analysis = out / "analysis-exec.json"
    print(f"\n[analyse] {len(record_files)} record file(s)", file=sys.stderr)
    res = subprocess.run([py, str(HERE / "analyze_exec.py"), *record_files,
                          "--json-out", str(analysis)], cwd=str(ROOT),
                         capture_output=True, text=True)
    report.write_text(res.stdout, "utf-8")
    sys.stdout.write(res.stdout)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        return res.returncode

    # 4. provenance manifest
    _write_manifest(out, proto, plan, record_files)
    print(f"\nreport:   {report}\nanalysis: {analysis}\nmanifest: {out / 'manifest.json'}", file=sys.stderr)
    return 0


def _write_manifest(out: Path, proto: dict, plan: list[dict], record_files: list[str]) -> None:
    import platform
    try:
        import httpx
        httpx_v = httpx.__version__
    except Exception:  # noqa: BLE001
        httpx_v = "(not importable)"
    import os
    samples_meta = []
    for p in plan:
        entry = {"slug": p["slug"], "stratum": p["stratum"], "language": p["language"],
                 "n": p["n"], "seed": p["seed"],
                 "recordsPresent": Path(p["records"]).exists()}
        if Path(p["sample"]).exists():
            try:
                doc = json.loads(Path(p["sample"]).read_text("utf-8"))
                entry["query"] = doc.get("query")
                entry["frameSize"] = doc.get("frameSize")
                entry["frameChecksum"] = doc.get("frameChecksum")
                entry["drawn"] = doc.get("drawn")
            except (ValueError, OSError):
                pass
        if Path(p["records"]).exists():
            entry["crawled"] = sum(1 for ln in Path(p["records"]).open() if ln.strip())
        samples_meta.append(entry)
    manifest = {
        "generated_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "protocol": {k: proto[k] for k in ("snapshot", "window_days", "seed_base", "frame_cap")},
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "httpx": httpx_v,
        "github_token_present": bool(os.environ.get("GITHUB_TOKEN")),
        "record_files": [Path(r).name for r in record_files],
        "samples": samples_meta,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), "utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
