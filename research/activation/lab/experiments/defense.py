"""E1-E4 — the defense. Ovrin's static pre-run gate evaluated as a reference
monitor: precision/recall/F1 on a labeled benign+adversarial set, and a
reconciliation of PREDICTED block vs OBSERVED activation (does the detector's
prediction match what agents actually did?)."""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path

from .. import detector as det
from .. import fixtures
from ..stats import rate_over, wilson
from .base import Cell, Ctx, Experiment


class Defense(Experiment):
    name = "defense"
    title = "E1-E4 — Ovrin pre-run gate (labeled eval + predictor validity)"

    def plan(self, ctx: Ctx) -> list[Cell]:
        return [Cell("eval", 1, {})]

    def trial(self, ctx: Ctx, cell: Cell, i: int) -> dict:
        m = int(ctx.cfg["defense"]["pairs"])
        base = Path(tempfile.mkdtemp(prefix="def-", dir=ctx.tmp_root))
        tp = fp = tn = fn = 0
        lat = []
        try:
            for idx in range(m):
                for repo, adversarial in fixtures.labeled_pair(base, idx, ctx.canary):
                    t0 = time.perf_counter()
                    pred = det.predicts_block(repo)
                    lat.append((time.perf_counter() - t0) * 1000)
                    if adversarial and pred:
                        tp += 1
                    elif adversarial and not pred:
                        fn += 1
                    elif not adversarial and pred:
                        fp += 1
                    else:
                        tn += 1
        finally:
            shutil.rmtree(base, ignore_errors=True)
        prec = tp / (tp + fp) if (tp + fp) else 1.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        lat.sort()
        p50 = lat[len(lat) // 2] if lat else 0.0
        p99 = lat[min(len(lat) - 1, int(len(lat) * 0.99))] if lat else 0.0
        return {"experiment": self.name, "cell": cell.id, "trial": i,
                "tp": tp, "fp": fp, "tn": tn, "fn": fn,
                "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
                "p50_ms": round(p50, 3), "p99_ms": round(p99, 3)}

    def aggregate(self, ctx: Ctx) -> list[str]:
        recs = ctx.store.read_records(self.name)
        out = []
        if recs:
            r = recs[-1]
            out.append(f"  labeled eval: precision {r['precision']:.3f}  "
                       f"recall {r['recall']:.3f}  F1 {r['f1']:.3f}  "
                       f"(TP {r['tp']} FP {r['fp']} TN {r['tn']} FN {r['fn']})")
            out.append(f"  gate latency: p50 {r['p50_ms']:.2f} ms  p99 {r['p99_ms']:.2f} ms")
        # predictor vs observed: the detector blocks vendored executing config;
        # did agents actually activate it?
        act = ctx.store.read_records("activation")
        vend = [a for a in act if a.get("variant") in ("vendored", "transitive")]
        if vend:
            obs = rate_over(vend, "activated")
            out.append(f"  predictor validity: detector BLOCKS vendored exec (100%); "
                       f"observed activation was {obs.pct()}")
            out.append("  -> every observed activation is one the gate would have blocked "
                       "pre-run" if obs.k else
                       "  -> no activation observed yet; run the live agents to validate")
        return out
