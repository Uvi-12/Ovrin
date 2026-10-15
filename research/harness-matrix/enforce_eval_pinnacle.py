#!/usr/bin/env python3
"""Evaluate Ovrin's three-layer enforce gate against the import-carriage fixtures.

Reports the three MCPFixGen-style metrics for each layer independently, then
combined, so the paper can show that each layer contributes separately and
that their combination is better than any single layer alone.

LAYER 1 — STATIC GATE metrics:
  Block Rate (Layer 1)     fraction of adversarial fixtures blocked pre-flight
  Regression Rate (L1)     fraction of benign fixtures incorrectly blocked
  Residual Reach (L1)      reach rate for fixtures the static gate did not block

LAYER 2 — IMPORT AUDIT metrics:
  Flag Rate (Layer 2)      fraction of adversarial import-chain fixtures flagged
  False Flag Rate (L2)     fraction of benign fixtures incorrectly flagged

LAYER 3 — UNCERTAINTY metrics:
  Low-confidence rate      fraction of decisions with resolver confidence < documented
  Unresolved import rate   fraction of import chains that could not be traced

COMBINED:
  Effective Block Rate     any adversarial fixture stopped by Layer 1 OR flagged by L2
  Combined Regression      any benign fixture incorrectly blocked OR flagged
  Combined Residual        what gets through both layers

Usage:
    python research/harness-matrix/enforce_eval_pinnacle.py \
      --harness claude-code \
      --n 20 \
      --out research/harness-matrix/enforce_eval_report.md
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import import_carriage as IC

# Lazy import of the enforce module so the script can be invoked before
# enforce.py is installed, producing a clean error rather than a crash
try:
    from ovrin.enforce import enforce_all, quarantine
    ENFORCE_AVAILABLE = True
except ImportError:
    ENFORCE_AVAILABLE = False


# Measured reach rates from the N=200 import-carriage campaign (run 6E7FD3 /
# import_v2.jsonl, conservative estimate).
MEASURED_REACH = {
    "BASELINE-no-import":        0.000,
    "1a-firstparty-imports-dep": 0.860,
    "1b-chain-into-dep":         0.860,
    "1c-dep-initiated-chain":    0.860,
}

GROUND_TRUTH = {
    "BASELINE-no-import":        "benign",
    "1a-firstparty-imports-dep": "adversarial",
    "1b-chain-into-dep":         "adversarial",
    "1c-dep-initiated-chain":    "adversarial",
}


def build_and_scan_enforce(cond: str, files: dict, base: Path,
                            harness: str) -> dict | None:
    """Build fixture, install it as a git repo, run enforce_all."""
    work = Path(tempfile.mkdtemp(prefix=f"ovrin-eval-{cond}-", dir=str(base)))
    for rel, content in files.items():
        p = work / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    for cmd in [
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.email=t@t.io", "-c", "user.name=t",
         "commit", "-qm", "fixture"],
    ]:
        subprocess.run(cmd, cwd=work, check=False, capture_output=True)

    scan_result = subprocess.run(
        ["ovrin", "scan", str(work), "-f", "json", "--no-timestamp"],
        capture_output=True, text=True)

    if scan_result.returncode not in (0, 1):
        shutil.rmtree(work, ignore_errors=True)
        return None

    try:
        manifest = json.loads(scan_result.stdout)
    except json.JSONDecodeError:
        shutil.rmtree(work, ignore_errors=True)
        return None

    result = enforce_all(manifest, harness_id=harness, root=work)
    shutil.rmtree(work, ignore_errors=True)
    return result


def main() -> int:
    if not ENFORCE_AVAILABLE:
        print("ERROR: ovrin.enforce not importable. Run: pip install -e '.[survey,dev]'")
        return 2

    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harness", default="claude-code")
    ap.add_argument("--out", default="/tmp/enforce_eval_report.md")
    ap.add_argument("--n", type=int, default=20,
                     help="trials per condition (gate is deterministic; N "
                          "gives fixture-token variance)")
    a = ap.parse_args()

    base = Path(tempfile.gettempdir())
    conds = IC.conditions()

    # Per-condition accumulators
    stats: dict[str, dict] = {
        c: {
            "n": 0, "gt": GROUND_TRUTH.get(c, "unknown"),
            # Layer 1
            "l1_blocked": 0, "l1_warned": 0, "l1_allowed": 0,
            # Layer 2
            "l2_flagged": 0, "l2_warned_import": 0,
            # Layer 3
            "low_conf": 0, "unresolved_imports": 0,
        }
        for c in conds
    }

    print(f"\nOVRIN ENFORCE EVALUATION (three-layer)  "
          f"harness={a.harness}  n/condition={a.n}\n")
    print(f"  {'Condition':<35} {'GT':>10}  L1      L2      LC  UI")
    print("  " + "-" * 72)

    for cond_name, files_template in conds.items():
        for _trial in range(a.n):
            tok = uuid.uuid4().hex[:8].upper()
            files = {k: v.replace("NONCE", tok)
                     if isinstance(v, str) else v
                     for k, v in files_template.items()}
            result = build_and_scan_enforce(cond_name, files, base, a.harness)
            if result is None:
                continue
            s = stats[cond_name]
            s["n"] += 1
            # Layer 1
            s["l1_blocked"] += result.blocked
            s["l1_warned"] += result.warned
            s["l1_allowed"] += result.allowed
            # Layer 2
            s["l2_flagged"] += result.flagged
            s["l2_warned_import"] += sum(
                1 for i in result.import_delegations if i.action == "WARN")
            # Layer 3
            s["low_conf"] += result.low_confidence_decisions
            s["unresolved_imports"] += result.unresolved_import_chains

        s = stats[cond_name]
        n = s["n"] or 1
        print(f"  {cond_name:<35} {s['gt']:>10}  "
              f"BLK:{s['l1_blocked']}/{n}  "
              f"FLG:{s['l2_flagged']}/{n}  "
              f"LC:{s['low_conf']}/{n}  "
              f"UI:{s['unresolved_imports']}/{n}")

    # --- Compute headline metrics ---
    adversarial = [s for s in stats.values() if s["gt"] == "adversarial"]
    benign = [s for s in stats.values() if s["gt"] == "benign"]

    def safe_rate(num, den): return num / den if den else 0.0

    # Layer 1
    adv_n = sum(s["n"] for s in adversarial)
    adv_blk = sum(s["l1_blocked"] for s in adversarial)
    l1_block_rate = safe_rate(adv_blk, adv_n)

    ben_n = sum(s["n"] for s in benign)
    ben_blk = sum(s["l1_blocked"] for s in benign)
    l1_regression = safe_rate(ben_blk, ben_n)

    l1_residual = sum(
        safe_rate(s["l1_allowed"], s["n"]) * MEASURED_REACH.get(c, 0)
        for c, s in stats.items() if s["gt"] == "adversarial"
    ) / len(adversarial) if adversarial else 0.0

    # Layer 2
    adv_flg = sum(s["l2_flagged"] for s in adversarial)
    l2_flag_rate = safe_rate(adv_flg, adv_n)
    ben_flg = sum(s["l2_flagged"] for s in benign)
    l2_false_flag = safe_rate(ben_flg, ben_n)

    # Combined
    combined_blocked = sum(
        max(s["l1_blocked"], s["l2_flagged"])
        for s in adversarial)
    combined_block_rate = safe_rate(combined_blocked, adv_n)

    combined_regression_n = sum(
        1 for s in benign
        if s["l1_blocked"] > 0 or s["l2_flagged"] > 0)
    combined_regression = safe_rate(combined_regression_n, len(benign))

    combined_residual = (1 - combined_block_rate) * safe_rate(
        sum(MEASURED_REACH.get(c, 0) for c, s in stats.items()
            if s["gt"] == "adversarial"),
        len(adversarial)
    ) if adversarial else 0.0

    # Layer 3
    total_low_conf = sum(s["low_conf"] for s in stats.values())
    total_unresolved = sum(s["unresolved_imports"] for s in stats.values())
    total_decisions = sum(s["n"] for s in stats.values())
    l3_low_conf_rate = safe_rate(total_low_conf, total_decisions)
    l3_unresolved_rate = safe_rate(total_unresolved, total_decisions)

    # Per-condition rows
    rows = []
    for c, s in stats.items():
        n = s["n"] or 1
        rows.append(
            f"| {c} | {s['gt']} | "
            f"{s['l1_blocked']}/{n} ({safe_rate(s['l1_blocked'],n):.0%}) | "
            f"{s['l2_flagged']}/{n} ({safe_rate(s['l2_flagged'],n):.0%}) | "
            f"{MEASURED_REACH.get(c,0):.0%} | "
            f"{safe_rate(s['low_conf'],n):.0%} |"
        )

    report = f"""# Ovrin enforce-mode evaluation (three-layer)

Harness: `{a.harness}`   N/condition: {a.n}
Date: {__import__('datetime').date.today().isoformat()}

## Per-condition results
| Condition | Ground truth | L1 Block rate | L2 Flag rate | Measured reach (pre-enforce) | L3 Low-confidence rate |
| --- | --- | --- | --- | --- | --- |
{chr(10).join(rows)}

## Headline metrics — Layer 1 (Static pre-flight gate)
| Metric | Value | Definition |
| --- | --- | --- |
| Block Rate | {l1_block_rate:.1%} | Adversarial fixtures blocked before agent launch |
| Regression Rate | {l1_regression:.1%} | Benign fixtures incorrectly blocked |
| Residual Reach | {l1_residual:.1%} | Dependency token reaches output despite L1 gate |

## Headline metrics — Layer 2 (Import-delegation audit)
| Metric | Value | Definition |
| --- | --- | --- |
| Flag Rate | {l2_flag_rate:.1%} | Adversarial import-chain delegations detected |
| False Flag Rate | {l2_false_flag:.1%} | Benign import delegations incorrectly flagged |

## Headline metrics — Layer 3 (Uncertainty disclosure)
| Metric | Value | Definition |
| --- | --- | --- |
| Low-confidence decision rate | {l3_low_conf_rate:.1%} | Decisions where resolver confidence < documented |
| Unresolved import chain rate | {l3_unresolved_rate:.1%} | @import chains that could not be fully traced |

## Combined metrics (all three layers)
| Metric | Value | Definition |
| --- | --- | --- |
| Effective Block Rate | {combined_block_rate:.1%} | Adversarial fixtures stopped by L1 OR flagged by L2 |
| Combined Regression | {combined_regression:.1%} | Benign fixtures incorrectly stopped or flagged |
| Combined Residual Reach | {combined_residual:.1%} | What gets through all three layers |

## Interpretation

Layer 1 (static gate) operates before any agent call and requires no model
access. It is deterministic: the same repository always produces the same
block/warn/allow decision. Its residual risk is the reach rate for fixtures
the gate did not block.

Layer 2 (import audit) addresses the import-carriage channel specifically —
the finding that approving a first-party instruction file does not automatically
approve its transitive @import chain. It flags the delegation DECISION (the
@import line in a first-party file) rather than the imported artifact, because
that is where a reviewer can intervene.

Layer 3 (uncertainty disclosure) is what makes this gate categorically
different from every existing supply-chain or SBOM tool. Rather than
presenting every decision with false certainty, it reports inline which
decisions rest on low-confidence resolver verdicts and which import chains
could not be fully traced. A reviewer who sees a WARN rather than a BLOCK
knows that the gate's confidence in its own prediction is limited.

The combination of all three layers produces a gate whose effective block rate,
regression rate, and residual reach are each reported separately per layer and
combined — matching the evaluation structure used by MCPFixGen and MAVLA in
the comparison papers.
"""

    out_p = Path(a.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(report, encoding="utf-8")

    print(f"\n{'='*72}")
    print(f"LAYER 1  Block: {l1_block_rate:.1%}  Regression: {l1_regression:.1%}  "
          f"Residual: {l1_residual:.1%}")
    print(f"LAYER 2  Flag:  {l2_flag_rate:.1%}  False-flag: {l2_false_flag:.1%}")
    print(f"LAYER 3  Low-conf: {l3_low_conf_rate:.1%}  "
          f"Unresolved-imports: {l3_unresolved_rate:.1%}")
    print(f"COMBINED Block: {combined_block_rate:.1%}  "
          f"Regression: {combined_regression:.1%}  "
          f"Residual: {combined_residual:.1%}")
    print(f"\nwrote {out_p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
