#!/usr/bin/env python3
"""Tier-1 close-out orchestrator — resumable. Runs the small deterministic-ish
harnesses (the workspace-trust experiment, bound A, bound B) N times each, skipping completed runs, and prints
a per-run verdict tally. These are trust/loading/restriction tests, not stochastic
rate tests, so N is small (default 5).

Resume: re-run the same command; run slots whose run0XX.md already exists are skipped.

  python research/harness-matrix/survey_runner.py --suite s4    --runs 5 --resume \
      --outdir tests/harness_cases/claude-code/s4
  python research/harness-matrix/survey_runner.py --suite boundA --runs 5 --resume \
      --outdir tests/harness_cases/claude-code/boundA
  python research/harness-matrix/survey_runner.py --suite boundB --runs 5 --resume \
      --outdir tests/harness_cases/claude-code/boundB
"""
from __future__ import annotations
import argparse, json, os, re, subprocess
from pathlib import Path

HARNESS = {
    "s4": "research/harness-matrix/workspace_trust_classification.py",
    "boundA": "research/harness-matrix/bound_autonomous.py",
    "boundB": "research/harness-matrix/bound_saferule.py",
    "s5": "research/harness-matrix/read_triggered_activation.py",
    "s6": "research/harness-matrix/version_rebinding.py",
}


def verdict_of(p: Path) -> str | None:
    if not p.exists():
        return None
    txt = p.read_text(errors="replace")
    m = re.search(r"## Verdict\s*\n\*\*(.+?)\*\*", txt, re.DOTALL)
    return m.group(1).strip().split(":")[0] if m else "(parsed, no verdict header)"


def run_once(suite: str, out_file: Path, agent_version: str) -> bool:
    cmd = ["python3", HARNESS[suite], "--out", str(out_file),
           "--agent-version", agent_version]
    try:
        subprocess.run(cmd, check=False, timeout=3600)
    except subprocess.TimeoutExpired:
        return False
    return out_file.exists()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", required=True, choices=list(HARNESS))
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--agent-version", default="unknown")
    a = ap.parse_args()

    outdir = Path(a.outdir); outdir.mkdir(parents=True, exist_ok=True)
    print(f"\nTIER1 RUNNER  suite={a.suite}  runs={a.runs}"
          f"{'  [resume]' if a.resume else ''}\n")
    tally: dict[str, int] = {}
    for i in range(1, a.runs + 1):
        rf = outdir / f"run{i:03d}.md"
        if a.resume and rf.exists():
            v = verdict_of(rf)
            tally[v] = tally.get(v, 0) + 1
            print(f"  run {i:>2}: [resumed] {v}")
            continue
        ok = run_once(a.suite, rf, a.agent_version)
        v = verdict_of(rf) if ok else "[failed]"
        tally[v] = tally.get(v, 0) + 1
        print(f"  run {i:>2}: {v}")

    print("\n  verdict tally:")
    for k, n in sorted(tally.items(), key=lambda x: -x[1]):
        print(f"    {n:>2}x  {k}")
    (outdir / "TALLY.json").write_text(json.dumps(tally, indent=2))
    print(f"\n  wrote {outdir/'TALLY.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
